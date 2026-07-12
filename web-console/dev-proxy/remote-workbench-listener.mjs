export async function startRemoteWorkbenchListener({
  loadRuntimeConfig,
  createVerifier,
  createServer,
  configRef,
  host,
  port,
} = {}) {
  if (
    typeof loadRuntimeConfig !== 'function'
    || typeof createVerifier !== 'function'
    || typeof createServer !== 'function'
    || !configRef
  ) {
    throw new Error('remote workbench listener dependencies are required');
  }
  const config = await loadRuntimeConfig();
  if (!config.remoteListenerReady) {
    configRef.current = config;
    return { config, server: null };
  }
  configRef.current = {
    ...config,
    reason: 'remote_listener_starting',
    remoteListenerReady: false,
  };
  const verifier = createVerifier(config.runtimePolicy);
  const server = createServer({ config, verifier });
  await new Promise((resolve, reject) => {
    const onError = (error) => {
      server.off('listening', onListening);
      reject(error);
    };
    const onListening = () => {
      server.off('error', onError);
      resolve();
    };
    server.once('error', onError);
    server.once('listening', onListening);
    server.listen(port, host);
  });
  configRef.current = config;
  return { config, server };
}
