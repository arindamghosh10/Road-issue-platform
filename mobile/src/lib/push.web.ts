// Web build (development/demo only): no push notifications. The Inbox still works.

export async function registerForPush(): Promise<void> {}
export async function unregisterPush(): Promise<void> {}
export function usePushHandlers(_signedIn: boolean) {}
