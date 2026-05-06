'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ChatCaptureWorkbenchModule0 from '@/app/capabilities/chat_capture/components/ChatCaptureWorkbench';

const componentModules: Record<string, Record<string, unknown>> = {
  "ChatCaptureWorkbench": ChatCaptureWorkbenchModule0 as Record<string, unknown>,
};

export default function ChatCaptureCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
