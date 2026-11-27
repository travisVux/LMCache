// Any other /api/* path: a JSON 404 (review 5.1: before this, Pages answered the 1 MB index page with 200 text/html).
import { E } from "../../lib/api.js";

export const onRequest = ({ request }) =>
  E("not_found", `no API at ${new URL(request.url).pathname} (see /api/db, /api/sync-status)`, 404);
