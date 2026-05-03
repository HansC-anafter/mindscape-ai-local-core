import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import AOLMeetingBottomShell from './AOLMeetingBottomShell';
import { attachResponse, summary } from './meetingWorkbenchTestData';
import { installAOLMeetingBottomShellTestHarness } from './meetingWorkbenchTestHarness';

describe('AOLMeetingBottomShell mention references', () => {
  installAOLMeetingBottomShellTestHarness();

  it('opens @ mention picker and inserts pack references into the command bar', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    await screen.findByTestId('meeting-pack-tool-select');
    const input = screen.getByLabelText('Meeting instruction');

    fireEvent.change(input, { target: { value: 'Use @' } });
    expect(screen.getByTestId('meeting-mention-picker')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId('meeting-mention-option-pack-visual_audit'));

    expect(input).toHaveValue('Use @pack:visual_audit ');
    expect(screen.getByTestId('meeting-pack-tool-select')).toHaveValue('visual_audit');
  });

  it('offers registry-backed storyboards, storyboard scenes, and character targets as command mentions', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');

    fireEvent.change(input, { target: { value: 'Send asset to @performance_di' } });
    expect(
      await screen.findByTestId('meeting-mention-option-registry-performance_direction-storyboard-pd_session_1'),
    ).toHaveTextContent('Yoga storyboard');
    fireEvent.mouseDown(screen.getByTestId('meeting-mention-option-registry-performance_direction-storyboard-pd_session_1'));
    expect(input).toHaveValue('Send asset to @storyboard:pd_session_1 ');

    fireEvent.change(input, { target: { value: 'Patch @sc02' } });
    expect(
      await screen.findByTestId(
        'meeting-mention-option-registry-performance_direction-storyboard_scene-pd_session_1_pd_artifact_1_sc02',
      ),
    ).toHaveTextContent('sc02');

    fireEvent.change(input, { target: { value: 'Use character @chacto' } });
    expect(
      await screen.findByTestId('meeting-mention-option-registry-character_training-character_package-chacto_hero_pkg'),
    ).toHaveTextContent('Chacto Hero');
    expect(screen.getByTestId('meeting-mention-option-registry-character_training-character_card-card_chacto')).toHaveTextContent(
      'Chacto Persona',
    );
    expect(
      vi.mocked(global.fetch).mock.calls.some(([calledUrl]) =>
        String(calledUrl).includes('/api/v1/capabilities/performance_direction/sessions'),
      ),
    ).toBe(false);
    expect(
      vi.mocked(global.fetch).mock.calls.some(([calledUrl]) =>
        String(calledUrl).includes('/api/v1/capabilities/character_training/'),
      ),
    ).toBe(false);
  });

  it('offers registry-backed object completion results in the command bar', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');
    fireEvent.change(input, { target: { value: 'Patch @registry' } });

    const option = await screen.findByTestId(
      'meeting-mention-option-registry-performance_direction-storyboard_scene-pd_session_registry_latest_sc03',
    );
    expect(option).toHaveTextContent('Registry storyboard / sc03');

    fireEvent.mouseDown(option);
    expect(input).toHaveValue('Patch @storyboard_scene:pd_session_registry:latest:sc03 ');
  });

  it('dispatches selected mention targets as structured meeting references', async () => {
    render(
      <AOLMeetingBottomShell
        workspaceId="ws-global"
        apiUrl="http://api.test"
        meetingId="mtg_global"
        summary={summary}
        selection={null}
        attachResponse={attachResponse}
        surfaceRoute="/workspaces/ws-global/capabilities/ig"
        onSwitchObject={vi.fn()}
      />,
    );

    const input = screen.getByLabelText('Meeting instruction');
    fireEvent.change(input, {
      target: { value: 'Generate generic asset @fixture' },
    });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-storyboard-fx_session_1'),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fx_scene` } });
    fireEvent.mouseDown(
      await screen.findByTestId(
        'meeting-mention-option-registry-fixture_pack-storyboard_scene-fx_session_1_fx_artifact_1_fx_scene',
      ),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fixture_character` } });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-character_package-fixture_character_pkg'),
    );

    fireEvent.change(input, { target: { value: `${(input as HTMLInputElement).value}@fixture_character_card` } });
    fireEvent.mouseDown(
      await screen.findByTestId('meeting-mention-option-registry-fixture_pack-character_card-fixture_character_card'),
    );

    fireEvent.click(screen.getByTestId('meeting-command-submit'));

    expect(await screen.findAllByText(/task-meeting/)).not.toHaveLength(0);
    const commandCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/meetings/mtg_global/commands'),
    );
    expect(commandCall).toBeDefined();
    const commandBody = JSON.parse(String(commandCall?.[1]?.body || '{}'));
    expect(commandBody.metadata.dispatch_mode).toBe('route_meeting_orchestration');
    expect(commandBody.context_objects).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'source' }),
        expect.objectContaining({ role: 'target' }),
        expect.objectContaining({ role: 'character' }),
      ]),
    );
    const chatCall = vi.mocked(global.fetch).mock.calls.find(([url]) => String(url).includes('/chat'));
    expect(chatCall).toBeUndefined();

    const invokeCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/object-actions/invoke'),
    );
    expect(invokeCall).toBeUndefined();

    const planCall = vi.mocked(global.fetch).mock.calls.find(([url]) =>
      String(url).includes('/object-actions/plan'),
    );
    expect(planCall).toBeUndefined();
  });


});
