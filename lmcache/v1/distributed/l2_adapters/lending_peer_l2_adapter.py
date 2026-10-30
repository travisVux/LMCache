# SPDX-License-Identifier: Apache-2.0
"""Peer adapters that lend a peer's bytes under the owner's read lock.

A copying peer adapter (:class:`~.p2p_l2_adapter.P2PL2Adapter`) moves a
looked-up object into this host's L1 and then releases the owner's read lock.
A leasing adapter keeps the owner's read lock for as long as readers here use
the object: the lookup reservation becomes the lease of a
:class:`~lmcache.v1.memory_management.BorrowedMemoryObj` that the shadow L1
indexes, and the unlock is sent when the last reader frees it.

:class:`LeasedPeerL2AdapterBase` owns what every such lender needs: the
owner's TTL bounded from this side, per-key reservations, the unlock worker
that batches releases, finalizers for objects dropped without ``release()``,
and the drain on teardown. A subclass decides what a borrowed object is
(:meth:`LeasedPeerL2AdapterBase._make_borrowed_object`) and when a lookup hit
is usable at all (:meth:`LeasedPeerL2AdapterBase._accept_address`).
"""

# Standard
from abc import abstractmethod
from collections import deque
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, cast
import math
import queue
import threading
import time
import weakref

# First Party
from lmcache.lmcache_native import Bitmap
from lmcache.logging import init_logger
from lmcache.v1.distributed.api import MemoryLayoutDesc, ObjectKey
from lmcache.v1.distributed.l2_adapters.base import L2TaskId
from lmcache.v1.distributed.l2_adapters.p2p_l2_adapter import (
    LendingPeerL2AdapterBase,
    PeerL2AdapterBase,
    PeerL2AdapterConfigBase,
)
from lmcache.v1.distributed.memory_manager import BorrowedMemoryObj
from lmcache.v1.distributed.transfer_channel.api import TransferChannelAddress
from lmcache.v1.memory_management import MemoryFormat, MemoryObj, MemoryObjMetadata

logger = init_logger(__name__)

# Stop trusting a borrowed object this long before the owner's read lock can
# expire: a GPU read that passed the last validity check must finish before
# the owner may reuse the bytes. Capped at a tenth of the TTL so short TTLs
# still leave a usable window.
_OWNER_TTL_MARGIN_S = 1.0


@dataclass
class _PendingUnlock:
    """Owner reservations waiting for the unlock worker.

    ``view`` is the finalizer of the borrowed object that held them, or None
    for reservations returned by ``submit_unlock`` without an object.
    """

    reservations: dict[ObjectKey, float]
    view: "weakref.finalize | None" = None


class LeasedPeerL2AdapterBase(LendingPeerL2AdapterBase):
    """Turn one peer's lookup reservations into leased, borrowed objects.

    Args:
        config: Peer RPC endpoint and lookup deadline.

    Every lookup hit adds one reservation for its key, with the owner's
    address and a local expiry. :meth:`take_borrowed_objects` moves one
    reservation per key into a borrowed object; :meth:`submit_unlock` returns
    one per key. Releases only enqueue work; a worker sends the unlock RPC
    outside L1 locks, batching everything queued since its last RPC so a slow
    or dead owner costs one timeout per batch, not per object.

    Thread model: lookups, borrows and ``submit_unlock`` run on the prefetch
    thread; object finalizers run on whichever thread drops the last
    reference, including inside garbage collection, so they take no lock and
    only put on a reentrant ``queue.SimpleQueue``.
    """

    def __init__(self, config: PeerL2AdapterConfigBase) -> None:
        # Lending state is set up before the base constructor runs the
        # region hook, per the PeerL2AdapterBase constructor contract.
        self._reservations: dict[
            ObjectKey, deque[tuple[TransferChannelAddress, float]]
        ] = {}
        # Guards _views and _pending_lookup_unlocks. Never taken by finalizers.
        self._borrow_lock = threading.Lock()
        # Finalizers of objects whose unlock the worker has not yet sent.
        self._views: set[weakref.finalize] = set()
        self._pending_lookup_unlocks = 0
        self._unlocks: queue.SimpleQueue[_PendingUnlock | None] = queue.SimpleQueue()
        self._unlock_worker = threading.Thread(
            target=self._run_unlocks, name="peer-unlock", daemon=True
        )
        self._unlock_worker.start()
        try:
            super().__init__(config)
        except BaseException:
            # The base released the RPC resources; stop the worker too.
            self._unlocks.put(None)
            self._unlock_worker.join()
            raise

    def submit_lookup_and_lock_task(
        self, keys: list[ObjectKey], group_layout_descs: dict[int, MemoryLayoutDesc]
    ) -> L2TaskId:
        """Submit an owner lookup whose hits this adapter will lend.

        Args:
            keys: Object keys to look up, without duplicates.
            group_layout_descs: Expected layouts indexed by object-group ID.

        Returns:
            The local lookup task ID.

        Raises:
            ValueError: If keys contain duplicates, which cannot identify
                independent reservations within one result dictionary.
        """
        if len(set(keys)) != len(keys):
            raise ValueError("Lookup keys of a lending adapter must be unique")
        return super().submit_lookup_and_lock_task(keys, group_layout_descs)

    def take_borrowed_objects(
        self, keys: list[ObjectKey], layouts: dict[int, MemoryLayoutDesc]
    ) -> dict[ObjectKey, BorrowedMemoryObj]:
        """Move one reservation per key into a borrowed object.

        Args:
            keys: Selected keys, at most once each.
            layouts: Expected layout by object-group ID.

        Returns:
            A borrowed object per key; its lease is the owner's reservation,
            ending at release or owner expiry (minus the margin). Keys with
            no reservation, a layout or size mismatch, or an expired
            reservation are omitted; the caller returns those with
            :meth:`submit_unlock`. No payload capacity is used.
        """
        objects: dict[ObjectKey, BorrowedMemoryObj] = {}
        for key in keys:
            held = self._reservations.get(key)
            if not held:
                continue
            address, expires = held[0]
            layout = layouts.get(key.object_group_id)
            if layout is None or time.monotonic() >= expires:
                continue
            size = sum(
                shape.numel() * dtype.itemsize
                for shape, dtype in zip(layout.shapes, layout.dtypes, strict=True)
            )
            if not layout.shapes or size != address.size:
                continue
            metadata = MemoryObjMetadata(
                shape=layout.shapes[0],
                dtype=layout.dtypes[0],
                address=address.offset,
                phy_size=size,
                ref_count=1,
                fmt=MemoryFormat.KV_2LTD,
                shapes=layout.shapes,
                dtypes=layout.dtypes,
            )
            pending = _PendingUnlock({key: expires})
            obj = self._make_borrowed_object(
                address,
                metadata,
                lease_is_valid=partial(self._lease_is_valid, pending, expires),
                on_release=partial(self._end_lease, pending),
            )
            if obj is None:
                continue
            self._pop_reservation(key)
            # Also ends the lease of an object dropped without release().
            pending.view = weakref.finalize(
                obj, self._release_view, weakref.ref(obj), pending
            )
            with self._borrow_lock:
                self._views.add(pending.view)
            objects[key] = obj
        return objects

    def submit_unlock(self, keys: list[ObjectKey], *, wait: bool = False) -> None:
        """Return one reservation per key to the owner, through the worker.

        Args:
            keys: Keys whose reservation to return; a key this adapter holds
                no reservation for (its hit was refused at lookup time, or
                became a borrowed object) is skipped.
            wait: Ignored; the worker always waits for the owner.
        """
        release: dict[ObjectKey, float] = {}
        for key in keys:
            held = self._reservations.get(key)
            if held:
                release[key] = self._pop_reservation(key)
        if release:
            self._queue_unlock(release)

    def submit_load_task(
        self,
        keys: list[ObjectKey],
        objects: list[MemoryObj],
    ) -> L2TaskId:
        """Reject copying; this adapter lends through take_borrowed_objects.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(f"{type(self).__name__} lends; it never copy-loads")

    def query_load_result(self, task_id: L2TaskId) -> Bitmap | None:
        """Reject load queries; see :meth:`submit_load_task`.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(f"{type(self).__name__} lends; it never copy-loads")

    def get_active_borrow_count(self) -> int:
        """Return borrowed objects and pending unlocks that must drain."""
        with self._borrow_lock:
            return len(self._views) + self._pending_lookup_unlocks

    def report_status(self) -> dict[str, Any]:
        """Return the peer endpoint and the outstanding borrow count."""
        return {
            **super().report_status(),
            "active_borrows": self.get_active_borrow_count(),
        }

    @abstractmethod
    def _accept_address(self, address: TransferChannelAddress) -> bool:
        """Return whether a valid lookup hit can be lent by this adapter."""

    @abstractmethod
    def _make_borrowed_object(
        self,
        address: TransferChannelAddress,
        metadata: MemoryObjMetadata,
        *,
        lease_is_valid: Callable[[], bool],
        on_release: Callable[[], None],
    ) -> BorrowedMemoryObj | None:
        """Build the borrowed object for one accepted hit, or None to skip it.

        Args:
            address: The owner's address of the object.
            metadata: Layout of the object; ``address`` and ``phy_size`` set.
            lease_is_valid: Lease check to hand to the object.
            on_release: Lease end to hand to the object.
        """

    def _drain_borrows_for_close(self) -> None:
        """Return every unborrowed reservation and stop the unlock worker.

        Called by a subclass's ``_unregister_peer_region`` before it releases
        the peer's region.

        Raises:
            RuntimeError: If an L1 still indexes live borrowed objects; the
                caller must drain them first.
        """
        with self._borrow_lock:
            if any(view.alive for view in self._views):
                raise RuntimeError(
                    f"Cannot close {type(self).__name__} with live borrowed objects"
                )
        for key, held in list(self._reservations.items()):
            for _, expires in held:
                self._queue_unlock({key: expires})
        self._reservations.clear()
        # The worker sends everything queued before this sentinel, then exits.
        # A retry after a failed teardown finds it stopped with nothing queued:
        # the first attempt returned every reservation and draining admits none.
        if self._unlock_worker.is_alive():
            self._unlocks.put(None)
            self._unlock_worker.join()

    def _process_lookup_result(
        self,
        task_id: L2TaskId,
        keys: list[ObjectKey],
        addresses: list[TransferChannelAddress],
        started_at: float,
    ) -> Bitmap:
        """Keep one reservation per hit with a locally bounded expiry."""
        result = Bitmap(len(keys))
        for i, (key, address) in enumerate(zip(keys, addresses, strict=True)):
            if not address.is_valid():
                continue
            ttl = address.read_ttl_seconds
            # Without a reported TTL the reservation never expires locally, so
            # its unlock is always sent (a lender may still refuse the hit).
            expires = (
                started_at + ttl - min(_OWNER_TTL_MARGIN_S, ttl / 10)
                if ttl > 0
                else math.inf
            )
            if not self._accept_address(address) or time.monotonic() >= expires:
                self._queue_unlock({key: expires})
            else:
                result.set(i)
                self._reservations.setdefault(key, deque()).append((address, expires))
        return result

    def _pop_reservation(self, key: ObjectKey) -> float:
        held = self._reservations[key]
        _, expires = held.popleft()
        if not held:
            del self._reservations[key]
        return expires

    def _lease_is_valid(self, pending: _PendingUnlock, expires: float) -> bool:
        """A lease ends at release or when the owner's lock may expire."""
        view = cast(weakref.finalize, pending.view)
        return view.alive and time.monotonic() < expires

    @staticmethod
    def _end_lease(pending: _PendingUnlock) -> None:
        # Calling the finalizer runs it at most once, also after GC ran it.
        cast(weakref.finalize, pending.view)()

    def _release_view(
        self,
        reference: weakref.ReferenceType[BorrowedMemoryObj],
        pending: _PendingUnlock,
    ) -> None:
        # Runs as a finalizer, possibly inside garbage collection: no locks.
        obj = reference()
        if obj is not None:
            obj.invalidate()
        self._unlocks.put(pending)

    def _queue_unlock(self, reservations: dict[ObjectKey, float]) -> None:
        with self._borrow_lock:
            self._pending_lookup_unlocks += 1
        self._unlocks.put(_PendingUnlock(reservations))

    def _run_unlocks(self) -> None:
        """Send queued unlocks in batches until the close sentinel arrives."""
        while True:
            batch = [self._unlocks.get()]
            while True:
                try:
                    batch.append(self._unlocks.get_nowait())
                except queue.Empty:
                    break
            pending = [item for item in batch if item is not None]
            # Expired reservations belong to the owner's TTL cleanup. A late
            # key-only unlock must not consume a subsequent borrow's count;
            # ``expires`` is early by the TTL margin, so skipping errs safe.
            now = time.monotonic()
            keys = [
                key
                for item in pending
                for key, expires in item.reservations.items()
                if now < expires
            ]
            if keys:
                try:
                    PeerL2AdapterBase.submit_unlock(self, keys, wait=True)
                except Exception:
                    logger.exception(
                        "Peer unlock failed; reservations follow the owner TTL"
                    )
            with self._borrow_lock:
                for item in pending:
                    if item.view is None:
                        self._pending_lookup_unlocks -= 1
                    else:
                        self._views.discard(item.view)
            if len(pending) < len(batch):
                return
