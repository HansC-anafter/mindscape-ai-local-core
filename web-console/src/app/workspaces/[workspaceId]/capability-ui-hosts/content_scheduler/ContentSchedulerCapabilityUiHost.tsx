'use client';

import CapabilityStaticLoadedComponents, {
  type StaticCapabilityUiHostProps,
} from '../CapabilityStaticLoadedComponents';
import * as ContentSchedulerPageModule0 from '@/app/capabilities/content_scheduler/components/ContentSchedulerPage';
import * as ScheduleCalendarModule1 from '@/app/capabilities/content_scheduler/components/ScheduleCalendar';

const componentModules: Record<string, Record<string, unknown>> = {
  "ContentSchedulerPage": ContentSchedulerPageModule0 as Record<string, unknown>,
  "ScheduleCalendar": ScheduleCalendarModule1 as Record<string, unknown>,
};

export default function ContentSchedulerCapabilityUiHost(props: StaticCapabilityUiHostProps) {
  return (
    <CapabilityStaticLoadedComponents
      {...props}
      componentModules={componentModules}
    />
  );
}
