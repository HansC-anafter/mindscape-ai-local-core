"""Native spatial action intent materialization helpers."""

from typing import Any, Dict, List, Optional


class NativeSpatialActionItemsMixin:
    def _extract_native_spatial_payload(
        self,
        decision: str,
    ) -> Optional[Dict[str, Any]]:
        """Extract the final native spatial planner JSON object from planner output."""
        payload = self._extract_json_payload(decision)
        if not isinstance(payload, dict):
            return None

        if not any(
            payload.get(key)
            for key in (
                "decision_summary",
                "actors",
                "objects",
                "anchors",
                "blocking_paths",
                "camera_blocking",
                "performance_beats",
                "interaction_beats",
                "active_segments",
            )
        ):
            return None
        return payload

    def _build_native_spatial_pd_action_intents(
        self,
        *,
        decision: str,
        user_message: str,
    ) -> List["ActionIntent"]:
        """Compatibility alias for native spatial PD planner materialization."""
        return self._build_native_spatial_action_intents(
            decision=decision,
            user_message=user_message,
        )

    def _build_native_spatial_action_intents(
        self,
        *,
        decision: str,
        user_message: str,
    ) -> List["ActionIntent"]:
        """Materialize native spatial planner JSON into typed meeting phases."""
        from backend.app.models.action_intent import ActionIntent, IntentConfidence

        payload = self._extract_native_spatial_payload(decision)
        if not payload:
            return []

        workspace_id = getattr(self.session, "workspace_id", None)
        decision_summary = str(
            payload.get("decision_summary") or user_message or "Native spatial plan"
        ).strip()
        actors = [
            item for item in list(payload.get("actors") or []) if isinstance(item, dict)
        ]
        objects = [
            item for item in list(payload.get("objects") or []) if isinstance(item, dict)
        ]
        anchors = [
            item for item in list(payload.get("anchors") or []) if isinstance(item, dict)
        ]
        blocking_paths = [
            item
            for item in list(payload.get("blocking_paths") or [])
            if isinstance(item, dict)
        ]
        performance_beats = [
            item
            for item in list(payload.get("performance_beats") or [])
            if isinstance(item, dict)
        ]
        interaction_beats = [
            item
            for item in list(payload.get("interaction_beats") or [])
            if isinstance(item, dict)
        ]
        active_segments = [
            item
            for item in list(payload.get("active_segments") or [])
            if isinstance(item, dict)
        ]
        camera_blocking = (
            dict(payload.get("camera_blocking") or {})
            if isinstance(payload.get("camera_blocking"), dict)
            else {}
        )
        verification_action = (
            dict(payload.get("verification_action_item") or {})
            if isinstance(payload.get("verification_action_item"), dict)
            else {}
        )

        def _clean_refs(*groups: Any) -> List[str]:
            refs: List[str] = []
            for group in groups:
                if isinstance(group, list):
                    values = group
                else:
                    values = [group]
                for raw in values:
                    if not isinstance(raw, str):
                        continue
                    value = raw.strip()
                    if value and value not in refs:
                        refs.append(value)
            return refs

        actor_ids = _clean_refs([item.get("id") for item in actors])
        object_ids = _clean_refs([item.get("id") for item in objects])
        anchor_ids = _clean_refs([item.get("id") for item in anchors])
        shared_refs = _clean_refs(actor_ids, object_ids, anchor_ids)
        entity_refs = _clean_refs(payload.get("entity_refs") or [], actor_ids, object_ids)

        message_lower = str(user_message or "").lower()
        if verification_action and (
            "exactly one" in message_lower
            or "one downstream action item" in message_lower
            or "one verification action item" in message_lower
        ):
            title = str(
                verification_action.get("title")
                or verification_action.get("deliverable")
                or "Verify Native Spatial Gate"
            ).strip()
            description = "\n".join(
                part
                for part in [
                    str(decision_summary or "").strip(),
                    str(verification_action.get("verification") or "").strip(),
                ]
                if part
            )
            return [
                ActionIntent(
                    intent_id="native.spatial.verification",
                    title=title[:120] or "Verify Native Spatial Gate",
                    description=description,
                    assignee=str(
                        verification_action.get("owner")
                        or verification_action.get("assigned_to")
                        or "reviewer"
                    ).strip(),
                    confidence=IntentConfidence.HIGH,
                    target_workspace_id=workspace_id,
                    priority="high",
                    asset_refs=_clean_refs(entity_refs, anchor_ids, shared_refs),
                    engine="manual:verification",
                    input_params={
                        "schedule_id": payload.get("schedule_id"),
                        "entity_refs": entity_refs,
                        "anchor_ids": anchor_ids,
                        "verification_action_item": verification_action,
                    },
                )
            ]

        intents: List[ActionIntent] = [
            ActionIntent(
                intent_id="native.spatial.plan",
                title="Freeze Native Spatial Plan",
                description=decision_summary,
                assignee="planner",
                confidence=IntentConfidence.HIGH,
                target_workspace_id=workspace_id,
                priority="high",
                asset_refs=shared_refs,
                engine="agent:auto",
            )
        ]
        last_intent_id = intents[-1].intent_id

        if len(active_segments) >= 2:
            for index, segment in enumerate(active_segments, start=1):
                segment_id = str(segment.get("segment_id") or f"segment.{index}").strip()
                title = str(segment.get("title") or segment_id).strip()
                entity_refs = _clean_refs(segment.get("entity_refs") or [])
                segment_anchor_ids = _clean_refs(segment.get("anchor_ids") or [])
                description_lines = [
                    f"Segment {segment_id} executes the beat '{title}'.",
                ]
                if entity_refs:
                    description_lines.append(
                        "Active entities: " + ", ".join(entity_refs)
                    )
                if segment_anchor_ids:
                    description_lines.append(
                        "Anchors: " + ", ".join(segment_anchor_ids)
                    )
                intents.append(
                    ActionIntent(
                        intent_id=segment_id,
                        title=title,
                        description="\n".join(description_lines),
                        assignee="planner",
                        confidence=IntentConfidence.HIGH,
                        target_workspace_id=workspace_id,
                        depends_on=[last_intent_id] if last_intent_id else None,
                        priority="high" if index == 1 else "medium",
                        asset_refs=_clean_refs(entity_refs, segment_anchor_ids),
                        engine="agent:auto",
                    )
                )
                last_intent_id = segment_id
            return intents

        for path_index, path in enumerate(blocking_paths, start=1):
            path_id = str(path.get("id") or f"path.{path_index}").strip()
            actor_ref = str(path.get("actor_ref") or "").strip()
            from_anchor = str(path.get("from_anchor") or "").strip()
            to_anchor = str(path.get("to_anchor") or "").strip()
            carried_object_ref = str(path.get("carried_object_ref") or "").strip()
            description = (
                f"Move {actor_ref or 'actor'} from {from_anchor or 'entry'} "
                f"to {to_anchor or 'destination'}"
            )
            if carried_object_ref:
                description += f" while carrying {carried_object_ref}."
            intents.append(
                ActionIntent(
                    intent_id=path_id,
                    title=f"Stage Blocking Path {path_id}",
                    description=description,
                    assignee="planner",
                    confidence=IntentConfidence.HIGH,
                    target_workspace_id=workspace_id,
                    depends_on=[last_intent_id] if last_intent_id else None,
                    priority="high",
                    asset_refs=_clean_refs(
                        actor_ref,
                        from_anchor,
                        to_anchor,
                        carried_object_ref,
                    ),
                    engine="agent:auto",
                )
            )
            last_intent_id = path_id

        if camera_blocking:
            camera_id = str(camera_blocking.get("camera_id") or "camera.main").strip()
            pattern = str(camera_blocking.get("pattern") or "camera_blocking").strip()
            keyframe_anchors = _clean_refs(
                [
                    frame.get("anchor_id")
                    for frame in list(camera_blocking.get("keyframes") or [])
                    if isinstance(frame, dict)
                ]
            )
            description = (
                f"Drive {camera_id} with {pattern} across anchors "
                f"{', '.join(keyframe_anchors) or 'scene anchors'}."
            )
            intents.append(
                ActionIntent(
                    intent_id=camera_id,
                    title=f"Stage Camera Blocking {camera_id}",
                    description=description,
                    assignee="planner",
                    confidence=IntentConfidence.HIGH,
                    target_workspace_id=workspace_id,
                    depends_on=[last_intent_id] if last_intent_id else None,
                    priority="high",
                    asset_refs=_clean_refs(camera_id, keyframe_anchors),
                    engine="agent:auto",
                )
            )
            last_intent_id = camera_id

        for beat_index, beat in enumerate(performance_beats, start=1):
            beat_id = str(beat.get("id") or f"beat.{beat_index}").strip()
            actor_ref = str(beat.get("actor_ref") or "").strip()
            object_ref = str(beat.get("object_ref") or "").strip()
            anchor_id = str(beat.get("anchor_id") or "").strip()
            intent_text = str(beat.get("intent") or "perform").strip()
            description = (
                f"Execute performance beat {beat_id}: {intent_text} "
                f"for {object_ref or 'scene object'} at {anchor_id or 'scene anchor'}."
            )
            if actor_ref:
                description = f"{actor_ref} executes {description}"
            intents.append(
                ActionIntent(
                    intent_id=beat_id,
                    title=f"Execute Performance Beat {beat_id}",
                    description=description,
                    assignee="planner",
                    confidence=IntentConfidence.HIGH,
                    target_workspace_id=workspace_id,
                    depends_on=[last_intent_id] if last_intent_id else None,
                    priority="medium",
                    asset_refs=_clean_refs(actor_ref, object_ref, anchor_id),
                    engine="agent:auto",
                )
            )
            last_intent_id = beat_id

        for beat_index, beat in enumerate(interaction_beats, start=1):
            beat_id = str(beat.get("id") or f"interaction.{beat_index}").strip()
            primary_ref = str(beat.get("primary_object_ref") or "").strip()
            secondary_ref = str(beat.get("secondary_object_ref") or "").strip()
            interaction = str(beat.get("interaction") or "interact").strip()
            description = (
                f"Resolve interaction {interaction} between "
                f"{primary_ref or 'primary object'} and {secondary_ref or 'secondary object'}."
            )
            intents.append(
                ActionIntent(
                    intent_id=beat_id,
                    title=f"Resolve Interaction {beat_id}",
                    description=description,
                    assignee="planner",
                    confidence=IntentConfidence.HIGH,
                    target_workspace_id=workspace_id,
                    depends_on=[last_intent_id] if last_intent_id else None,
                    priority="medium",
                    asset_refs=_clean_refs(primary_ref, secondary_ref),
                    engine="agent:auto",
                )
            )
            last_intent_id = beat_id

        return intents
