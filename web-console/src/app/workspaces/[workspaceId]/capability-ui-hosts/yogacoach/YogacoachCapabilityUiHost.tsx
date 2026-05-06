'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as CourseWorkbenchModule0 from '@/app/capabilities/yogacoach/components/CourseWorkbench';
import * as TeacherVideoUploadModule1 from '@/app/capabilities/yogacoach/components/TeacherVideoUpload';
import * as PageModule2 from '@/app/capabilities/yogacoach/page';

const componentModules: Record<string, Record<string, unknown>> = {
  "CourseWorkbench": CourseWorkbenchModule0 as Record<string, unknown>,
  "TeacherVideoUpload": TeacherVideoUploadModule1 as Record<string, unknown>,
  "page": PageModule2 as Record<string, unknown>,
};

export default function YogacoachCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
