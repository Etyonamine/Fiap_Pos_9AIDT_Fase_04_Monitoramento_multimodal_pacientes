import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function processor(rate = 16000) {
  let Registered;
  const messages = [];
  class AudioWorkletProcessor {
    port = {
      postMessage: (message, transfer) => messages.push({ message, transfer }),
      onmessage: null,
    };
  }
  vm.runInNewContext(
    readFileSync(new URL('../public/camera-audio-processor.js', import.meta.url), 'utf8'),
    {
      AudioWorkletProcessor, Float32Array, sampleRate: rate,
      registerProcessor: (name, type) => {
        assert.equal(name, 'camera-audio-processor');
        Registered = type;
      },
    },
    { filename: 'camera-audio-processor.js' },
  );
  return { instance: new Registered(), messages };
}

test('actual worklet averages channels without feedback and stays alive with no input', () => {
  const { instance, messages } = processor();
  assert.equal(instance.process([]), true);
  assert.equal(instance.process([[]]), true);
  assert.equal(messages.length, 0);
  instance.process([[new Float32Array([1, -.5]), new Float32Array([-1, .5])]]);
  instance.port.onmessage({ data: 'flush' });
  assert.deepEqual([...messages[0].message.samples], [0, 0]);
  assert.equal(messages[0].transfer[0], messages[0].message.samples.buffer);
  assert.equal(messages[1].message.flushed, true);
  assert.equal(instance.length, 0);
  assert.equal(instance.samples.length, 0);
});

for (const rate of [16000, 48000]) {
  test(`actual worklet batches three seconds at ${rate} Hz without dropping samples`, () => {
    const { instance, messages } = processor(rate);
    instance.process([[new Float32Array(rate * 3 - 1).fill(.25)]]);
    assert.equal(messages.length, 0);
    instance.process([[new Float32Array([.75])]]);
    assert.equal(messages.length, 1);
    assert.equal(messages[0].message.samples.length, rate * 3);
    assert.equal(messages[0].message.samples.at(-1), .75);
    assert.equal(messages[0].message.samples[0], .25);
    assert.equal(instance.length, 0);
  });
}

test('flush drains the final partial chunk once; repeated flush acknowledges without duplicates', () => {
  const { instance, messages } = processor();
  instance.process([[new Float32Array([.1, .2])]]);
  instance.process([[new Float32Array([.3])]]);
  instance.port.onmessage({ data: 'ignored' });
  assert.equal(messages.length, 0);
  instance.port.onmessage({ data: 'flush' });
  instance.port.onmessage({ data: 'flush' });
  assert.equal(messages.filter(item => item.message.samples).length, 1);
  assert.equal(messages.filter(item => item.message.flushed).length, 2);
  assert.deepEqual([...messages[0].message.samples], [...new Float32Array([.1, .2, .3])]);
});
