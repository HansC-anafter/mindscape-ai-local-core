import type { RelayPublisherState } from "./types.js";

export function inferPublisherState({
    streamName,
    relayRunning,
    recentOutput,
}: {
    streamName: string;
    relayRunning: boolean;
    recentOutput: string[];
}): RelayPublisherState {
    if (!relayRunning) {
        return {
            stream_name: streamName,
            has_publisher: false,
            state: "relay_not_running",
            reason: "relay_not_running",
            detail: "Start the RTMP relay before checking for an external publisher.",
        };
    }

    const escapedStreamName = streamName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const publishingPattern = new RegExp(`publishing to path ['"]?${escapedStreamName}['"]?`, "i");
    const notConfiguredPattern = new RegExp(`path ['"]?${escapedStreamName}['"]? is not configured`, "i");
    if (recentOutput.some((line) => publishingPattern.test(line))) {
        return {
            stream_name: streamName,
            has_publisher: true,
            state: "publishing",
            detail: "The relay has an active publisher for this stream.",
        };
    }

    const missingPath = recentOutput.some((line) => notConfiguredPattern.test(line));
    return {
        stream_name: streamName,
        has_publisher: false,
        state: "waiting_for_publisher",
        reason: missingPath ? "no_publisher_for_stream" : "publisher_not_detected",
        detail: missingPath
            ? "OBS requested the stream, but no external RTMP publisher is connected to this path."
            : "The relay is ready, but no external RTMP publisher has been detected yet.",
    };
}
