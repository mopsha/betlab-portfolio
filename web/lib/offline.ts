// The service worker's saved pages (public/sw.js, PAGES): one account's Today, Live and Me must not open offline for the
// next person on a shared device. Signing out is a server action, whose redirect the worker never sees as a navigation,
// so the page clears the cache itself (and tells the worker), on Sign out and whenever the sign-in page opens.
export const SAVED_PAGES = "betlab-pages-1";

export async function forgetSavedPages(): Promise<void> {
  try {
    if (typeof caches !== "undefined") await caches.delete(SAVED_PAGES);
    navigator.serviceWorker?.controller?.postMessage({ type: "signed-out" });
  } catch { /* no cache API here (private mode): nothing was saved */ }
}
