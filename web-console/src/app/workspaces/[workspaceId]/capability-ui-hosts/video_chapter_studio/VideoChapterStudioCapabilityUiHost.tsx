'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ChapterDetailPanelModule0 from '@/app/capabilities/video_chapter_studio/components/ChapterDetailPanel';
import * as ChapterListPanelModule1 from '@/app/capabilities/video_chapter_studio/components/ChapterListPanel';
import * as ChapterStudioPageModule2 from '@/app/capabilities/video_chapter_studio/components/ChapterStudioPage';
import * as PoseOverlayVideoPlayerModule3 from '@/app/capabilities/video_chapter_studio/components/PoseOverlayVideoPlayer';
import * as TimelineModule4 from '@/app/capabilities/video_chapter_studio/components/Timeline';
import * as VideoChapterStudioModule5 from '@/app/capabilities/video_chapter_studio/components/VideoChapterStudio';
import * as VideoPlayerModule6 from '@/app/capabilities/video_chapter_studio/components/VideoPlayer';
import * as WorkbenchLayoutModule7 from '@/app/capabilities/video_chapter_studio/components/WorkbenchLayout';

const componentModules: Record<string, Record<string, unknown>> = {
  "ChapterDetailPanel": ChapterDetailPanelModule0 as Record<string, unknown>,
  "ChapterListPanel": ChapterListPanelModule1 as Record<string, unknown>,
  "ChapterStudioPage": ChapterStudioPageModule2 as Record<string, unknown>,
  "PoseOverlayVideoPlayer": PoseOverlayVideoPlayerModule3 as Record<string, unknown>,
  "Timeline": TimelineModule4 as Record<string, unknown>,
  "VideoChapterStudio": VideoChapterStudioModule5 as Record<string, unknown>,
  "VideoPlayer": VideoPlayerModule6 as Record<string, unknown>,
  "WorkbenchLayout": WorkbenchLayoutModule7 as Record<string, unknown>,
};

export default function VideoChapterStudioCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
