'use client';

const PROVIDER_CONNECTION_STEPS = [
  {
    title: 'USB webcam source',
    body: 'Use a camera that appears in the browser device list, then select Computer / OBS camera below.',
  },
  {
    title: 'Network stream relay',
    body: 'Start a host relay such as MediaMTX, add the relay stream to OBS as a Media Source, then expose OBS Virtual Camera.',
  },
  {
    title: 'Gimbal-mounted camera',
    body: 'Connect the mounted camera through USB, a capture card, or OBS. The gimbal itself does not consume this pairing code.',
  },
];

export function ExternalProviderConnectionGuide() {
  return (
    <div
      className="mt-2 rounded border border-sky-200 bg-sky-50 p-2 text-[11px] leading-4 text-sky-950 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-100"
      data-testid="external-provider-connection-guide"
    >
      <div className="font-semibold">External provider connection guide</div>
      <ol className="mt-1 space-y-1">
        {PROVIDER_CONNECTION_STEPS.map((step, index) => (
          <li key={step.title}>
            <span className="font-semibold">{index + 1}. {step.title}:</span>{' '}
            <span>{step.body}</span>
          </li>
        ))}
      </ol>
      <div className="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
        Do not paste this code into a camera or gimbal. The code is only for a
        bridge app or host tool that can publish a browser-compatible source.
      </div>
    </div>
  );
}

export default ExternalProviderConnectionGuide;
