class WorkspacePcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkSize = 4096;
    this.chunk = new Float32Array(this.chunkSize);
    this.offset = 0;
    this.closed = false;
    this.port.onmessage = (event) => {
      if (event.data?.type !== 'flush' || this.closed) {
        return;
      }
      this.closed = true;
      if (this.offset > 0) {
        const remaining = this.chunk.slice(0, this.offset);
        this.port.postMessage({ type: 'samples', samples: remaining }, [remaining.buffer]);
      }
      this.port.postMessage({ type: 'flushed' });
    };
  }

  process(inputs) {
    if (this.closed) {
      return false;
    }
    const samples = inputs[0]?.[0];
    if (!samples) {
      return true;
    }
    let sourceOffset = 0;
    while (sourceOffset < samples.length) {
      const writable = Math.min(
        this.chunkSize - this.offset,
        samples.length - sourceOffset,
      );
      this.chunk.set(samples.subarray(sourceOffset, sourceOffset + writable), this.offset);
      this.offset += writable;
      sourceOffset += writable;
      if (this.offset === this.chunkSize) {
        const completed = this.chunk;
        this.port.postMessage({ type: 'samples', samples: completed }, [completed.buffer]);
        this.chunk = new Float32Array(this.chunkSize);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor('workspace-pcm-capture', WorkspacePcmCaptureProcessor);
