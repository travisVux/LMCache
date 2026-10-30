# SPDX-License-Identifier: Apache-2.0
"""The borrowed objects a lender hands over (local views and remote handles),
and the memory manager that frees them."""

# Standard
from typing import Callable
import abc

# Third Party
import torch

# First Party
from lmcache.v1.distributed.api import MemoryLayoutDesc
from lmcache.v1.distributed.error import L1Error
from lmcache.v1.distributed.internal_api import L1MemoryDesc
from lmcache.v1.memory_management import (
    MemoryFormat,
    MemoryObj,
    MemoryObjMetadata,
    TensorMemoryObj,
)


class BorrowedMemoryObj(MemoryObj):
    """A memory object held under a lease that someone else grants.

    The lender (e.g. an L2 adapter holding a peer's read reservation) decides
    how long the bytes stay valid: ``is_valid()`` is False once the lease
    ended, and :meth:`release` ends it from this side. A lender must release
    an object that is garbage-collected without :meth:`release`. Subclasses
    set ``_lease_is_valid`` and ``_on_release`` in their constructor.
    """

    _lease_is_valid: Callable[[], bool]
    _on_release: Callable[[], None]

    @property
    def lease(self) -> tuple[Callable[[], bool], Callable[[], None]]:
        """Return the object's ``(lease_is_valid, on_release)`` pair."""
        return self._lease_is_valid, self._on_release

    def replace_lease(
        self, lease_is_valid: Callable[[], bool], on_release: Callable[[], None]
    ) -> None:
        """Put the object under another lease, a newer reservation of the
        same bytes. The caller owns the previous lease.

        Args:
            lease_is_valid: Nonblocking check that the new lease still holds.
            on_release: Ends the new lease; same rules as the constructor's.
        """
        self._lease_is_valid = lease_is_valid
        self._on_release = on_release

    def release(self) -> None:
        """Invalidate the object and end the lease; repeated calls are no-ops."""
        self.invalidate()
        self._on_release()

    @abc.abstractmethod
    def same_bytes(self, other: "BorrowedMemoryObj") -> bool:
        """Return whether ``other`` is a view of the same bytes as this one,
        so that a shadow L1 may renew this object from ``other``'s lease."""
        raise NotImplementedError

    @abc.abstractmethod
    def local_device(self) -> torch.device | None:
        """Return the device a reader touches the bytes on, or None when the
        bytes are read wherever the reader lands them."""
        raise NotImplementedError


class BorrowedTensorMemoryObj(TensorMemoryObj, BorrowedMemoryObj):
    """A tensor view of bytes another party owns, held under a lease.

    It allocates nothing locally. Whoever lends the bytes (e.g. an L2 adapter
    holding a peer's read reservation) supplies the lease: ``is_valid()``
    also reports whether the lease still holds, and ``release`` ends it.

    Args:
        raw_data: The borrowed bytes; a view, never a copy.
        metadata: Layout of the object.
        lease_is_valid: Nonblocking check that the lease still holds.
        on_release: Ends the lease; idempotent, nonblocking, and takes no lock
            the caller might hold. It runs under the L1 manager's lock, on
            whichever thread frees the view, so it must never call back into
            an L1 manager and may only submit the peer unlock, never wait for
            it.
    """

    def __init__(
        self,
        raw_data: torch.Tensor,
        metadata: MemoryObjMetadata,
        *,
        lease_is_valid: Callable[[], bool],
        on_release: Callable[[], None],
    ) -> None:
        super().__init__(raw_data, metadata, parent_allocator=None)
        self._lease_is_valid = lease_is_valid
        self._on_release = on_release

    def same_bytes(self, other: BorrowedMemoryObj) -> bool:
        """Both views alias one buffer of one size."""
        return (
            isinstance(other, BorrowedTensorMemoryObj)
            and self.raw_data.data_ptr() == other.raw_data.data_ptr()
            and self.get_size() == other.get_size()
        )

    def local_device(self) -> torch.device:
        """The device the aliased buffer lives on."""
        return self.raw_data.device

    def is_valid(self) -> bool:
        """Return whether the view is unreleased and its lease still holds."""
        return super().is_valid() and self._lease_is_valid()


class PendingRead(abc.ABC):
    """A read of a remote object into local device memory, in flight."""

    @abc.abstractmethod
    def is_finished(self) -> bool:
        """Return whether the read reached a terminal state."""
        raise NotImplementedError

    @abc.abstractmethod
    def succeeded(self) -> bool:
        """Return whether a finished read delivered every byte."""
        raise NotImplementedError


class RemoteBorrowedMemoryObj(BorrowedMemoryObj):
    """A borrowed object whose bytes stay on the lender's host.

    Nothing local backs it: ``tensor`` is None and ``data_ptr`` raises. A
    reader moves the bytes with :meth:`read_into`, which the lender serves
    (e.g. an RDMA read of a peer's DRAM straight into GPU memory).

    Args:
        metadata: Layout of the object; ``address`` is the lender-relative
            offset and ``phy_size`` the byte length.
        lease_is_valid: Nonblocking check that the lease still holds.
        on_release: Ends the lease; idempotent, nonblocking, and takes no lock
            the caller might hold.
        read_into: Starts a read of the whole object into a registered local
            region at a byte offset; see :meth:`read_into`.
    """

    def __init__(
        self,
        metadata: MemoryObjMetadata,
        *,
        lease_is_valid: Callable[[], bool],
        on_release: Callable[[], None],
        read_into: Callable[[int, int], PendingRead],
    ) -> None:
        super().__init__(metadata)
        self.valid = True
        self._lease_is_valid = lease_is_valid
        self._on_release = on_release
        self._read_into = read_into

    def read_into(self, region_id: int, offset: int) -> PendingRead:
        """Start reading the object into a registered local memory region.

        Args:
            region_id: Local region registered with the lender's transport
                (e.g. the GPU staging buffer).
            offset: Byte offset of the destination within that region.

        Returns:
            The in-flight read; poll it until finished. It fails instead of
            reading when the lease has already ended.
        """
        return self._read_into(region_id, offset)

    def same_bytes(self, other: BorrowedMemoryObj) -> bool:
        """Same lender-relative address and length: the same remote bytes."""
        return (
            isinstance(other, RemoteBorrowedMemoryObj)
            and self.meta.address == other.meta.address
            and self.meta.phy_size == other.meta.phy_size
        )

    def local_device(self) -> None:
        """Read wherever the reader lands it, so every device may hold it."""
        return None

    def invalidate(self) -> None:
        self.valid = False

    def is_valid(self) -> bool:
        """Return whether the object is unreleased and its lease still holds."""
        return self.valid and self._lease_is_valid()

    def get_size(self) -> int:
        return self.meta.get_size()

    def get_shape(self) -> torch.Size:
        return self.meta.shape

    def get_dtype(self) -> torch.dtype | None:
        return self.meta.dtype

    def get_shapes(self) -> list[torch.Size]:
        return (
            list(self.meta.shapes)
            if self.meta.shapes is not None
            else [self.meta.shape]
        )

    def get_dtypes(self) -> list[torch.dtype]:
        if self.meta.dtypes is not None:
            return list(self.meta.dtypes)
        if self.meta.dtype is None:
            raise ValueError("Remote borrowed object has no dtype")
        return [self.meta.dtype]

    def get_memory_format(self) -> MemoryFormat:
        return self.meta.fmt

    def get_physical_size(self) -> int:
        return self.meta.phy_size

    def ref_count_up(self) -> None:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    def ref_count_down(self) -> None:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    def get_ref_count(self) -> int:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    def get_num_tokens(self) -> int:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    def pin(self) -> bool:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    def unpin(self) -> bool:
        raise NotImplementedError("RemoteBorrowedMemoryObj has no local allocation")

    @property
    def metadata(self) -> MemoryObjMetadata:
        return self.meta

    @property
    def is_pinned(self) -> bool:
        return False

    @property
    def can_evict(self) -> bool:
        return True

    @property
    def tensor(self) -> torch.Tensor | None:
        return None

    @property
    def raw_tensor(self) -> torch.Tensor | None:
        return None

    def get_tensor(self, index: int) -> torch.Tensor | None:
        return None

    @property
    def byte_array(self) -> bytes:
        raise NotImplementedError("RemoteBorrowedMemoryObj holds no local bytes")

    @property
    def data_ptr(self) -> int:
        raise NotImplementedError("RemoteBorrowedMemoryObj holds no local bytes")

    @property
    def shm_offset(self) -> int:
        raise NotImplementedError("RemoteBorrowedMemoryObj holds no local bytes")

    @property
    def shm_byte_length(self) -> int:
        raise NotImplementedError("RemoteBorrowedMemoryObj holds no local bytes")

    def parent(self) -> None:
        return None


class ShadowL1MemoryManager:
    """Memory manager behind :class:`ShadowL1Manager`.

    Its objects are :class:`BorrowedMemoryObj` views whose bytes someone else
    owns, so it never allocates and has no capacity; freeing an object ends
    its lease. Satisfies ``L1MemoryManagerProtocol``.
    """

    def allocate(
        self, layout_desc: MemoryLayoutDesc, count: int
    ) -> tuple[L1Error, list[MemoryObj]]:
        """Refuse every allocation; views enter through ``ShadowL1Manager.admit``.

        Args:
            layout_desc: Ignored.
            count: Ignored.

        Returns:
            ``(OUT_OF_MEMORY, [])``, always.
        """
        return L1Error.OUT_OF_MEMORY, []

    def free(self, mem_objs: list[MemoryObj]) -> L1Error:
        """End each view's lease.

        Args:
            mem_objs: Borrowed views to release.

        Returns:
            ``SUCCESS``.

        Raises:
            TypeError: If an object is not a :class:`BorrowedMemoryObj`,
                which would mean a wiring bug placed local memory here.
        """
        for obj in mem_objs:
            if not isinstance(obj, BorrowedMemoryObj):
                raise TypeError(f"Shadow L1 holds only borrowed views, got {obj!r}")
            obj.release()
        return L1Error.SUCCESS

    def get_memory_usage(self) -> tuple[int, int]:
        """Return ``(0, 0)``: borrowed bytes are not local memory."""
        return 0, 0

    def get_l1_memory_desc(self) -> L1MemoryDesc | None:
        """Return None; there is no local buffer to register."""
        return None

    def close(self) -> None:
        """Do nothing; there is nothing to unmap."""

    def memcheck(self) -> bool:
        """Return True; there is no allocator bookkeeping to check."""
        return True
