/**
 * Stable Meeting command submission facade.
 *
 * Callers import this seam; route settlement and transport details remain owned by
 * the controller module so the workbench shell does not accumulate compound logic.
 */
export {
  createMeetingCommandSubmitHandler,
  settleMeetingCommandAcceptance,
  submitCompiledCompositionGraphCommand,
  type CreateMeetingCommandSubmitHandlerArgs,
  type SettleMeetingCommandAcceptanceArgs,
} from './meetingCommandSubmissionController';
