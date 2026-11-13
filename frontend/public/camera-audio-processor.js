class CameraAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.length = 0;
    this.port.onmessage = ({ data }) => {
      if (data === 'flush') {
        this.flush();
        this.port.postMessage({ flushed: true });
      }
    };
  }
  flush() {
    if (!this.length) return;
    const samples = new Float32Array(this.length);
    let offset = 0;
    for (const chunk of this.samples) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }
    this.port.postMessage({ samples }, [samples.buffer]);
    this.samples = [];
    this.length = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (channels?.length) {
      const mono = new Float32Array(channels[0].length);
      for (const channel of channels) {
        for (let i = 0; i < mono.length; i++) mono[i] += channel[i] / channels.length;
      }
      this.samples.push(mono);
      this.length += mono.length;
      if (this.length >= sampleRate * 3) this.flush();
    }
    return true;
  }
}
registerProcessor('camera-audio-processor', CameraAudioProcessor);
