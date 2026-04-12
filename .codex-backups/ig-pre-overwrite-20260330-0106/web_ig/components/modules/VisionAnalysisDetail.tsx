import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Copy, Download, Check } from 'lucide-react';

type DetailTab = 'analysis' | 'annotations' | 'thinking' | 'raw';
const DETAIL_TABS: Array<{ id: DetailTab; label: string }> = [
  { id: 'analysis', label: 'Summary' },
  { id: 'annotations', label: '標註' },
  { id: 'thinking', label: 'Thinking' },
  { id: 'raw', label: 'Raw' },
];

function compactText(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function joinText(values: unknown[], separator = ' · '): string {
  return values.map(compactText).filter(Boolean).join(separator);
}

function formatConfidence(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? `${Math.round(value * 100)}%`
    : '';
}

function formatClothingItem(item: any): string {
  const garment = compactText(item?.garment_type);
  const details = [item?.color, item?.material, item?.fit, item?.style_era]
    .map((value, index) => (index >= 2 ? formatEnumLabel(value) : compactText(value)))
    .filter(Boolean);
  if (garment) {
    return details.length > 0 ? `${garment} (${details.join(', ')})` : garment;
  }
  return details.join(', ');
}

function formatPropItem(item: any): string {
  const name = compactText(item?.name);
  const details = joinText([formatEnumLabel(item?.usage), formatEnumLabel(item?.region)]);
  if (name) {
    return details ? `${name} (${details})` : name;
  }
  return details;
}

function formatMaterialItem(item: any): string {
  const material = joinText([formatEnumLabel(item?.material_type), formatEnumLabel(item?.surface_finish)], ' / ');
  const region = formatEnumLabel(item?.region);
  const confidence = formatConfidence(item?.confidence);
  return joinText(
    [material, region ? `region: ${region}` : '', confidence],
    ' · ',
  );
}

function formatCoverage(coverage: any): string {
  if (!coverage) return '';
  const chestMethod = formatEnumLabel(coverage?.chest_coverage_method);
  const chestVisibility = formatEnumLabel(coverage?.chest_visibility);
  const chestLabel = chestVisibility
    ? `${chestVisibility}${chestMethod ? ` via ${chestMethod}` : ''}`
    : chestMethod;
  return joinText(
    [
      coverage?.upper_body_coverage ? `upper: ${formatEnumLabel(coverage.upper_body_coverage)}` : '',
      coverage?.lower_body_coverage ? `lower: ${formatEnumLabel(coverage.lower_body_coverage)}` : '',
      chestLabel ? `chest: ${chestLabel}` : '',
      coverage?.coverage_notes ? `note: ${coverage.coverage_notes}` : '',
    ],
    ' · ',
  );
}

function formatEvidenceList(values: unknown): string {
  if (!Array.isArray(values)) return '';
  return values.map(compactText).filter(Boolean).join(' | ');
}

function formatEnumLabel(value: unknown): string {
  return compactText(value).replace(/_/g, ' ');
}

function formatEnumList(values: unknown): string {
  if (!Array.isArray(values)) return '';
  return values.map(formatEnumLabel).filter(Boolean).join(', ');
}

function formatBodyType(value: unknown): string {
  return formatEnumLabel(value);
}

function formatDemographics(subj: any): string {
  return [
    subj?.skin_tone ? `skin: ${formatEnumLabel(subj.skin_tone)}` : '',
    subj?.perceived_ethnicity ? `ethnicity: ${formatEnumLabel(subj.perceived_ethnicity)}` : '',
    subj?.face_shape ? `face: ${formatEnumLabel(subj.face_shape)}` : '',
  ].filter(Boolean).join(' · ');
}

function formatHair(hair: any): string {
  if (!hair) return '';
  return [
    compactText(hair?.color),
    formatEnumLabel(hair?.length),
    formatEnumLabel(hair?.style),
    formatEnumLabel(hair?.texture),
  ].filter(Boolean).join(', ');
}

function formatPose(pose: any): string {
  if (!pose) return '';
  return [
    formatEnumLabel(pose?.stance),
    formatEnumLabel(pose?.body_orientation),
    pose?.gaze_direction ? `gaze ${formatEnumLabel(pose.gaze_direction)}` : '',
    pose?.gesture ? `gesture: ${compactText(pose.gesture)}` : '',
  ].filter(Boolean).join(' · ');
}

function formatLightSource(lightSource: any): string {
  if (!lightSource) return '';
  return [
    formatEnumLabel(lightSource?.source_type),
    formatEnumLabel(lightSource?.direction),
    formatEnumLabel(lightSource?.color_temperature),
    formatEnumLabel(lightSource?.intensity),
  ].filter(Boolean).join(' · ');
}

function formatSubjectIdentity(subj: any): string {
  return [
    formatEnumLabel(subj?.gender_presentation),
    subj?.estimated_age_range ? `age ${compactText(subj.estimated_age_range)}` : '',
    formatEnumLabel(subj?.expression),
  ].filter(Boolean).join(' · ');
}

// ── Markdown formatter ──
export function formatVisionAsMarkdown(ref: any): string {
  const vd = ref.vision_description;
  if (!vd) return '';

  const lines: string[] = [];
  const shortcode = ref.source_shortcode || 'unknown';
  lines.push(`# Vision Analysis: ${shortcode}`);
  
  const provVersion = ref.analysis_provenance?.schema_version;
  lines.push(`**Schema:** ${provVersion || vd.schema_version || '1.0'}`);
  lines.push('');

  if (vd.raw_description) {
    lines.push(`> ${vd.raw_description}`);
    lines.push('');
  }

  // Scene
  if (vd.scene) {
    lines.push('## 🎬 Scene');
    if (vd.scene.composition) lines.push(`- **Composition:** ${formatEnumLabel(vd.scene.composition)}`);
    if (vd.scene.lighting) lines.push(`- **Lighting:** ${formatEnumLabel(vd.scene.lighting)}`);
    if (vd.scene.setting) lines.push(`- **Setting:** ${formatEnumLabel(vd.scene.setting)}`);
    if (vd.scene.mood) lines.push(`- **Mood:** ${formatEnumLabel(vd.scene.mood)}`);
    if (vd.scene.camera_angle) lines.push(`- **Camera:** ${formatEnumLabel(vd.scene.camera_angle)}`);
    if (vd.scene.summary) lines.push(`- **Summary:** ${vd.scene.summary}`);
    if (vd.scene.evidence_notes?.length > 0) {
      lines.push(`- **Evidence:** ${formatEvidenceList(vd.scene.evidence_notes)}`);
    }
    lines.push('');
  }

  // Objects
  if (vd.objects?.objects?.length > 0) {
    lines.push(`## 🔍 Objects (${vd.objects.object_count || vd.objects.objects.length})`);
    for (const obj of vd.objects.objects) {
      lines.push(`- **${obj.label}** — ${Math.round(obj.confidence * 100)}% (${obj.region})`);
    }
    if (vd.objects.dominant_subject) {
      lines.push(`\n*Subject: ${formatEnumLabel(vd.objects.dominant_subject)}*`);
    }
    lines.push('');
  }

  // Style
  if (vd.style) {
    lines.push('## 🎨 Style');
    if (vd.style.dominant_colors?.length > 0) {
      lines.push(`- **Dominant Colors:** ${formatEnumList(vd.style.dominant_colors)}`);
    }
    if (vd.style.typography) {
      lines.push(`- **Typography:** ${vd.style.typography}`);
    }
    if (vd.style.visual_techniques?.length > 0) {
      lines.push(`- **Techniques:** ${formatEnumList(vd.style.visual_techniques)}`);
    }
    if (vd.style.aesthetic_tags?.length > 0) {
      lines.push(`- **Aesthetic:** ${formatEnumList(vd.style.aesthetic_tags)}`);
    }
    if (vd.style.instagram_style) {
      lines.push(`- **IG Style:** ${formatEnumLabel(vd.style.instagram_style)}`);
    }
    lines.push('');
  }

  // Insights
  if (vd.insights) {
    lines.push('## 💡 Insights');
    if (vd.insights.engagement) lines.push(`- **Engagement:** ${vd.insights.engagement}`);
    if (vd.insights.reverse_prompt) lines.push(`- **Prompt:** ${vd.insights.reverse_prompt}`);
    if (vd.insights.brands?.length > 0) lines.push(`- **Brands:** ${vd.insights.brands.join(', ')}`);
    if (vd.insights.hashtags?.length > 0) lines.push(`- **Hashtags:** ${vd.insights.hashtags.join(' ')}`);
    lines.push('');
  }

  // ── V2.0 ──

  // Subjects
  if (vd.subjects?.length > 0) {
    lines.push(`## 👤 Subjects (${vd.subjects.length})`);
    for (const [i, subj] of vd.subjects.entries()) {
      const identity = formatSubjectIdentity(subj);
      lines.push(`### Subject ${i + 1}: ${identity || 'Unknown'}`);
      if (subj.body_type) {
        lines.push(`- **Body:** ${formatBodyType(subj.body_type)}`);
      }
      if (subj.skin_tone || subj.perceived_ethnicity || subj.face_shape) {
        lines.push(`- **Demographics:** ${formatDemographics(subj)}`);
      }
      if (subj.facial_features) {
        lines.push(`- **Facial Features:** ${subj.facial_features}`);
      }
      if (subj.hair && (subj.hair.color || subj.hair.length || subj.hair.style || subj.hair.texture)) {
        lines.push(`- **Hair:** ${formatHair(subj.hair)}`);
      }
      if (subj.clothing?.length > 0) {
        lines.push(`- **Clothing:** ${subj.clothing.map((c: any) => formatClothingItem(c)).filter(Boolean).join(', ')}`);
      }
      if (subj.coverage) {
        const coverageText = formatCoverage(subj.coverage);
        if (coverageText) lines.push(`- **Coverage:** ${coverageText}`);
      }
      if (subj.negative_observations?.length > 0) {
        lines.push(`- **Negative Observations:** ${subj.negative_observations.map(formatEnumLabel).filter(Boolean).join(' | ')}`);
      }
      if (subj.accessories?.length > 0) {
        lines.push(`- **Accessories:** ${subj.accessories.map(formatEnumLabel).filter(Boolean).join(', ')}`);
      }
      if (subj.pose && (subj.pose.stance || subj.pose.gaze_direction || subj.pose.gesture || subj.pose.body_orientation)) {
        lines.push(`- **Pose:** ${formatPose(subj.pose)}`);
      }
      if (subj.archetype_tags?.length > 0) {
        lines.push(`- **Archetype:** ${formatEnumList(subj.archetype_tags)}`);
      }
      if (subj.evidence_notes?.length > 0) {
        lines.push(`- **Evidence:** ${formatEvidenceList(subj.evidence_notes)}`);
      }
    }
    lines.push('');
  }

  // Camera Tech
  if (vd.camera_tech) {
    lines.push('## 📸 Camera Tech');
    const ct = vd.camera_tech;
    if (ct.focal_length_class) lines.push(`- **Focal:** ${formatEnumLabel(ct.focal_length_class)}${ct.focal_length_mm_range ? ` (${ct.focal_length_mm_range})` : ''}`);
    if (ct.depth_of_field) lines.push(`- **DoF:** ${formatEnumLabel(ct.depth_of_field)}`);
    if (ct.estimated_aperture) lines.push(`- **Aperture:** ${ct.estimated_aperture}`);
    if (ct.shot_type) lines.push(`- **Shot:** ${formatEnumLabel(ct.shot_type)}`);
    if (ct.shutter_effect) lines.push(`- **Shutter:** ${formatEnumLabel(ct.shutter_effect)}`);
    if (ct.camera_movement) lines.push(`- **Movement:** ${formatEnumLabel(ct.camera_movement)}`);
    if (ct.aspect_ratio) lines.push(`- **Ratio:** ${ct.aspect_ratio}`);
    if (ct.framing) {
      const framing = [
        ct.framing.rule_of_thirds && 'Rule of Thirds',
        ct.framing.symmetry && 'Symmetry',
        ct.framing.leading_lines && 'Leading Lines',
        ct.framing.negative_space_ratio && `Space: ${ct.framing.negative_space_ratio}`,
      ].filter(Boolean);
      if (framing.length > 0) lines.push(`- **Framing:** ${framing.join(', ')}`);
    }
    if (ct.evidence_notes?.length > 0) {
      lines.push(`- **Evidence:** ${formatEvidenceList(ct.evidence_notes)}`);
    }
    lines.push('');
  }

  // Environment
  if (vd.environment) {
    lines.push('## 🌍 Environment');
    const env = vd.environment;
    if (env.location_type) lines.push(`- **Location:** ${formatEnumLabel(env.location_type)}${env.location_subtype ? ` / ${formatEnumLabel(env.location_subtype)}` : ''}`);
    if (env.time_of_day) lines.push(`- **Time:** ${formatEnumLabel(env.time_of_day)}`);
    if (env.weather_atmosphere) lines.push(`- **Weather:** ${formatEnumLabel(env.weather_atmosphere)}`);
    if (env.foreground_elements?.length > 0) lines.push(`- **FG:** ${formatEnumList(env.foreground_elements)}`);
    if (env.midground_elements?.length > 0) lines.push(`- **MG:** ${formatEnumList(env.midground_elements)}`);
    if (env.background_elements?.length > 0) lines.push(`- **BG:** ${formatEnumList(env.background_elements)}`);
    if (env.interactive_props?.length > 0) lines.push(`- **Props:** ${env.interactive_props.map((p: any) => formatPropItem(p)).filter(Boolean).join(', ')}`);
    if (env.set_dressing?.length > 0) lines.push(`- **Set Dressing:** ${formatEnumList(env.set_dressing)}`);
    if (env.light_source?.source_type) {
      lines.push(`- **Light:** ${formatLightSource(env.light_source)}`);
    }
    if (env.evidence_notes?.length > 0) {
      lines.push(`- **Evidence:** ${formatEvidenceList(env.evidence_notes)}`);
    }
    lines.push('');
  }

  // Material
  if (vd.material?.materials?.length > 0) {
    lines.push('## 🧱 Material');
    for (const m of vd.material.materials) {
      const materialLabel = formatMaterialItem(m);
      if (materialLabel) lines.push(`- ${materialLabel}`);
    }
    if (vd.material.texture_notes) lines.push(`\n*${vd.material.texture_notes}*`);
    lines.push('');
  }

  if (vd.product_interaction && (
    vd.product_interaction.product_visible ||
    vd.product_interaction.product_category ||
    vd.product_interaction.interaction_type ||
    vd.product_interaction.placement_region ||
    vd.product_interaction.brand_visible
  )) {
    lines.push('## 🛍️ Product Interaction');
    if (vd.product_interaction.product_visible) lines.push('- **Product Visible:** yes');
    if (vd.product_interaction.product_category) lines.push(`- **Category:** ${formatEnumLabel(vd.product_interaction.product_category)}`);
    if (vd.product_interaction.interaction_type) lines.push(`- **Interaction:** ${formatEnumLabel(vd.product_interaction.interaction_type)}`);
    if (vd.product_interaction.placement_region) lines.push(`- **Placement:** ${formatEnumLabel(vd.product_interaction.placement_region)}`);
    if (vd.product_interaction.brand_visible) lines.push('- **Brand Visible:** yes');
    lines.push('');
  }

  if (vd.safety_flags && (
    (vd.safety_flags.nsfw_risk && vd.safety_flags.nsfw_risk !== 'none') ||
    vd.safety_flags.medical_claims ||
    vd.safety_flags.copyright_concerns
  )) {
    lines.push('## ⚠️ Safety');
    if (vd.safety_flags.nsfw_risk && vd.safety_flags.nsfw_risk !== 'none') {
      lines.push(`- **NSFW Risk:** ${formatEnumLabel(vd.safety_flags.nsfw_risk)}`);
    }
    if (vd.safety_flags.medical_claims) lines.push('- **Medical Claims:** yes');
    if (vd.safety_flags.copyright_concerns) lines.push(`- **Copyright:** ${vd.safety_flags.copyright_concerns}`);
    lines.push('');
  }

  const uncertaintyLabel = formatConfidence(vd.uncertainty);
  if (uncertaintyLabel) {
    lines.push('## 📏 Confidence');
    lines.push(`- **Uncertainty:** ${uncertaintyLabel}`);
    lines.push('');
  }

  // Tags
  if (ref.tags?.length > 0 || ref.auto_tags?.length > 0) {
    lines.push('## 🏷️ Tags');
    if (ref.tags?.length > 0) lines.push(`**Manual:** ${ref.tags.join(', ')}`);
    if (ref.auto_tags?.length > 0) lines.push(`**Auto:** ${ref.auto_tags.join(', ')}`);
  }

  return lines.join('\n');
}

function hasTrainingAnnotations(value: any): boolean {
  if (!value || typeof value !== 'object') return false;
  const scalarFields = [
    value.training_readiness,
    value.training_source_kind,
    value.dataset_mix_role,
    value.identity_signal_strength,
    value.primary_subject_clarity,
    value.subject_framing,
    value.face_angle,
    value.face_visibility,
    value.occlusion_level,
    value.style_strength,
    value.identity_drift_risk,
    value.look_variant_level,
    value.identity_cluster_hint,
    value.look_state_hint,
    value.training_notes,
  ];
  if (scalarFields.some((item) => compactText(item))) {
    return true;
  }
  return [
    value.training_lane_hints,
    value.style_tags,
    value.quality_flags,
    value.hard_blockers,
    value.reject_reasons,
  ].some((items) => Array.isArray(items) && items.some((item) => compactText(item)));
}

export function formatTrainingAnnotationsAsMarkdown(ref: any): string {
  const ta = ref?.training_annotations || ref?.vision_description?.training_annotations;
  if (!hasTrainingAnnotations(ta)) return '';

  const lines: string[] = [];
  const shortcode = ref?.source_shortcode || 'unknown';
  lines.push(`# Training Annotations: ${shortcode}`);
  lines.push('');

  if (ta.training_readiness) {
    lines.push(`- **Readiness:** ${formatEnumLabel(ta.training_readiness)}`);
  }
  if (ta.training_source_kind) {
    lines.push(`- **Source Kind:** ${formatEnumLabel(ta.training_source_kind)}`);
  }
  if (ta.dataset_mix_role) {
    lines.push(`- **Dataset Role:** ${formatEnumLabel(ta.dataset_mix_role)}`);
  }
  if (ta.identity_signal_strength) {
    lines.push(`- **Identity Signal Strength:** ${formatEnumLabel(ta.identity_signal_strength)}`);
  }
  if (ta.primary_subject_clarity) {
    lines.push(`- **Primary Subject Clarity:** ${formatEnumLabel(ta.primary_subject_clarity)}`);
  }
  if (Array.isArray(ta.training_lane_hints) && ta.training_lane_hints.length > 0) {
    lines.push(`- **Lane Hints:** ${ta.training_lane_hints.map(formatEnumLabel).filter(Boolean).join(', ')}`);
  }
  if (ta.subject_framing) {
    lines.push(`- **Subject Framing:** ${formatEnumLabel(ta.subject_framing)}`);
  }
  if (ta.face_angle) {
    lines.push(`- **Face Angle:** ${formatEnumLabel(ta.face_angle)}`);
  }
  if (ta.face_visibility) {
    lines.push(`- **Face Visibility:** ${formatEnumLabel(ta.face_visibility)}`);
  }
  if (ta.occlusion_level) {
    lines.push(`- **Occlusion:** ${formatEnumLabel(ta.occlusion_level)}`);
  }
  if (ta.style_strength) {
    lines.push(`- **Style Strength:** ${formatEnumLabel(ta.style_strength)}`);
  }
  if (ta.identity_drift_risk) {
    lines.push(`- **Identity Drift Risk:** ${formatEnumLabel(ta.identity_drift_risk)}`);
  }
  if (ta.look_variant_level) {
    lines.push(`- **Look Variant Level:** ${formatEnumLabel(ta.look_variant_level)}`);
  }
  if (Array.isArray(ta.style_tags) && ta.style_tags.length > 0) {
    lines.push(`- **Style Tags:** ${ta.style_tags.map(formatEnumLabel).filter(Boolean).join(', ')}`);
  }
  if (Array.isArray(ta.quality_flags) && ta.quality_flags.length > 0) {
    lines.push(`- **Quality Flags:** ${ta.quality_flags.map(formatEnumLabel).filter(Boolean).join(', ')}`);
  }
  if (Array.isArray(ta.hard_blockers) && ta.hard_blockers.length > 0) {
    lines.push(`- **Hard Blockers:** ${ta.hard_blockers.map(formatEnumLabel).filter(Boolean).join(', ')}`);
  }
  if (Array.isArray(ta.reject_reasons) && ta.reject_reasons.length > 0) {
    lines.push(`- **Reject Reasons:** ${ta.reject_reasons.map(formatEnumLabel).filter(Boolean).join(', ')}`);
  }
  if (ta.identity_cluster_hint) {
    lines.push(`- **Identity Cluster Hint:** ${ta.identity_cluster_hint}`);
  }
  if (ta.look_state_hint) {
    lines.push(`- **Look State Hint:** ${ta.look_state_hint}`);
  }
  if (ta.training_notes) {
    lines.push(`- **Notes:** ${ta.training_notes}`);
  }

  return lines.join('\n');
}

export function formatDetailTabText(
  ref: any,
  activeTab: DetailTab,
  thinkingText: string,
  rawText: string,
  failureReason: string,
  failureStage: string,
): string {
  if (activeTab === 'analysis') {
    return formatVisionAsMarkdown(ref);
  }

  if (activeTab === 'annotations') {
    return formatTrainingAnnotationsAsMarkdown(ref);
  }

  if (activeTab === 'thinking') {
    return thinkingText;
  }

  const lines: string[] = [];
  const shortcode = ref?.source_shortcode || 'unknown';
  lines.push(`# Raw Model Output: ${shortcode}`);
  lines.push('');
  if (failureStage) lines.push(`Failure Stage: ${failureStage}`);
  if (failureReason) lines.push(`Failure Reason: ${failureReason}`);
  if (failureStage || failureReason) lines.push('');
  if (rawText) lines.push(rawText);
  return lines.join('\n');
}

// ── Component ──
interface VisionAnalysisDetailProps {
  detailRef: any;
  imageUrl?: string | null;
}

function getImageExtension(contentType: string): string {
  if (contentType.includes('png')) return 'png';
  if (contentType.includes('webp')) return 'webp';
  if (contentType.includes('gif')) return 'gif';
  if (contentType.includes('jpeg') || contentType.includes('jpg')) return 'jpg';
  return 'jpg';
}

export default function VisionAnalysisDetail({ detailRef, imageUrl }: VisionAnalysisDetailProps) {
  const [copied, setCopied] = useState(false);
  const [downloadingImage, setDownloadingImage] = useState(false);
  const [activeTab, setActiveTab] = useState<DetailTab>('analysis');
  const vd = detailRef?.vision_description;
  const trainingAnnotations = detailRef?.training_annotations || vd?.training_annotations;
  const debug = detailRef?.analysis_debug;
  const thinkingText = ((debug?.thinking_text as string) || (vd?._thinking as string) || '').trim();
  const rawText = ((debug?.raw_text as string) || '').trim();
  const failureStage = ((debug?.failure_stage as string) || '').trim();
  const failureReason = ((detailRef?.analysis_job?.last_error as string) || (debug?.failure_reason as string) || '').trim();
  const schemaLabel = (detailRef?.analysis_provenance?.schema_version as string) || (vd?.schema_version as string) || '';
  const uncertaintyLabel = formatConfidence(vd?.uncertainty);
  const showProductInteraction = Boolean(
    vd?.product_interaction && (
      vd.product_interaction.product_visible ||
      vd.product_interaction.product_category ||
      vd.product_interaction.interaction_type ||
      vd.product_interaction.placement_region ||
      vd.product_interaction.brand_visible
    ),
  );
  const showSafetyFlags = Boolean(
    vd?.safety_flags && (
      (vd.safety_flags.nsfw_risk && vd.safety_flags.nsfw_risk !== 'none') ||
      vd.safety_flags.medical_claims ||
      vd.safety_flags.copyright_concerns
    ),
  );
  const hasAnalysis = Boolean(vd);
  const hasAnnotations = hasTrainingAnnotations(trainingAnnotations);
  const hasThinking = thinkingText.length > 0;
  const hasRaw = rawText.length > 0 || failureReason.length > 0 || failureStage.length > 0;
  const availableTabIds = useMemo(
    () => [
      ...(hasAnalysis ? (['analysis'] as DetailTab[]) : []),
      ...(hasAnnotations ? (['annotations'] as DetailTab[]) : []),
      ...(hasThinking ? (['thinking'] as DetailTab[]) : []),
      ...(hasRaw ? (['raw'] as DetailTab[]) : []),
    ],
    [hasAnalysis, hasAnnotations, hasRaw, hasThinking],
  );

  useEffect(() => {
    if (availableTabIds.length === 0) return;
    if (!availableTabIds.includes(activeTab)) {
      setActiveTab(availableTabIds[0]);
    }
  }, [activeTab, availableTabIds]);

  const handleCopy = useCallback(() => {
    const text = formatDetailTabText(
      detailRef,
      activeTab,
      thinkingText,
      rawText,
      failureReason,
      failureStage,
    );
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [activeTab, detailRef, failureReason, failureStage, rawText, thinkingText]);

  const handleExportMd = useCallback(() => {
    const text = formatDetailTabText(
      detailRef,
      activeTab,
      thinkingText,
      rawText,
      failureReason,
      failureStage,
    );
    const filenameBase = `vision_${detailRef.source_shortcode || 'analysis'}`;
    const markdownTab = activeTab === 'analysis' || activeTab === 'annotations';
    const extension = markdownTab ? 'md' : 'txt';
    const mime = markdownTab ? 'text/markdown;charset=utf-8' : 'text/plain;charset=utf-8';
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filenameBase}_${activeTab}.${extension}`;
    a.click();
    URL.revokeObjectURL(url);
  }, [activeTab, detailRef, failureReason, failureStage, rawText, thinkingText]);

  const handleDownloadImage = useCallback(async () => {
    if (!imageUrl || downloadingImage) return;
    setDownloadingImage(true);
    try {
      const response = await fetch(imageUrl);
      if (!response.ok) {
        throw new Error(`Image download failed: ${response.status}`);
      }
      const blob = await response.blob();
      const extension = getImageExtension(blob.type || '');
      const filenameBase = `vision_${detailRef.source_shortcode || detailRef.reference_id || 'image'}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${filenameBase}.${extension}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('[VisionAnalysisDetail] Failed to download image:', error);
      window.open(imageUrl, '_blank', 'noopener,noreferrer');
    } finally {
      setDownloadingImage(false);
    }
  }, [detailRef.reference_id, detailRef.source_shortcode, downloadingImage, imageUrl]);

  if (!hasAnalysis && !hasAnnotations && !hasThinking && !hasRaw) {
    return (
      <p className="text-sm text-gray-400 py-4 text-center">
        尚未分析（status: {detailRef?.analysis_status || 'N/A'}）
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Action buttons */}
      <div className="flex gap-2 justify-end">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          title="複製分析結果"
        >
          {copied ? <Check size={12} className="text-green-500" /> : <Copy size={12} />}
          {copied ? '已複製' : '複製'}
        </button>
        <button
          onClick={handleExportMd}
          className="flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          title="匯出為 Markdown"
        >
          <Download size={12} />
          {activeTab === 'analysis' ? '.md' : '.txt'}
        </button>
        {imageUrl && (
          <button
            onClick={handleDownloadImage}
            disabled={downloadingImage}
            className="flex items-center gap-1 text-[11px] px-2 py-1 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="下載圖片"
          >
            <Download size={12} />
            {downloadingImage ? '下載中' : '圖片'}
          </button>
        )}
      </div>
      <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-1">
          {DETAIL_TABS.map((tab) => {
            const disabled = !availableTabIds.includes(tab.id);
            return (
            <button
              key={tab.id}
              onClick={() => {
                if (!disabled) setActiveTab(tab.id);
              }}
              disabled={disabled}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
                  : disabled
                    ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === 'analysis' && vd && (
        <>
      {/* Summary */}
      <p className="text-sm text-gray-700 dark:text-gray-300 italic">
        {vd.raw_description || vd.scene?.summary}
      </p>
      {(schemaLabel || uncertaintyLabel) && (
        <div className="flex flex-wrap gap-1">
          {schemaLabel && (
            <span className="text-[10px] bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 px-1.5 py-0.5 rounded">
              Schema {schemaLabel}
            </span>
          )}
          {uncertaintyLabel && (
            <span className="text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded">
              Uncertainty {uncertaintyLabel}
            </span>
          )}
        </div>
      )}

      {/* Scene */}
      {vd.scene && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">🎬 Scene</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
            <div><span className="font-medium">Composition:</span> {formatEnumLabel(vd.scene.composition)}</div>
            <div><span className="font-medium">Lighting:</span> {formatEnumLabel(vd.scene.lighting)}</div>
            <div><span className="font-medium">Setting:</span> {formatEnumLabel(vd.scene.setting)}</div>
            <div><span className="font-medium">Mood:</span> {formatEnumLabel(vd.scene.mood)}</div>
            <div><span className="font-medium">Camera:</span> {formatEnumLabel(vd.scene.camera_angle)}</div>
            {vd.scene.summary && (
              <div><span className="font-medium">Summary:</span> {vd.scene.summary}</div>
            )}
          </div>
          {vd.scene.evidence_notes?.length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              Evidence: {formatEvidenceList(vd.scene.evidence_notes)}
            </div>
          )}
        </div>
      )}

      {/* Objects */}
      {vd.objects?.objects?.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">
            🔍 Objects ({vd.objects.object_count})
          </h4>
          <div className="space-y-1">
            {vd.objects.objects.map((obj: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-gray-700 dark:text-gray-300 font-medium">{obj.label}</span>
                <span className="text-gray-400">{Math.round(obj.confidence * 100)}%</span>
                <span className="text-gray-400 italic">{obj.region}</span>
              </div>
            ))}
          </div>
          {vd.objects.dominant_subject && (
            <p className="text-xs text-gray-500 mt-2 italic">
              Subject: {formatEnumLabel(vd.objects.dominant_subject)}
            </p>
          )}
        </div>
      )}

      {/* Style */}
      {vd.style && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">🎨 Style</h4>
          {vd.style.color_palette?.length > 0 && (
            <div className="flex gap-1 mb-2">
              {vd.style.color_palette.map((c: string) => (
                <div key={c} className="w-6 h-6 rounded border" style={{ backgroundColor: c }} title={c} />
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-1">
            {vd.style.dominant_colors?.map((t: string) => (
              <span key={`dc-${t}`} className="text-[10px] bg-sky-100 dark:bg-sky-900/30 text-sky-600 px-1.5 py-0.5 rounded">{formatEnumLabel(t)}</span>
            ))}
            {vd.style.visual_techniques?.map((t: string) => (
              <span key={t} className="text-[10px] bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 px-1.5 py-0.5 rounded">{formatEnumLabel(t)}</span>
            ))}
            {vd.style.aesthetic_tags?.map((t: string) => (
              <span key={t} className="text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-600 px-1.5 py-0.5 rounded">{formatEnumLabel(t)}</span>
            ))}
          </div>
          {vd.style.typography && (
            <p className="text-xs text-gray-500 mt-2">Typography: {vd.style.typography}</p>
          )}
          {vd.style.instagram_style && (
            <p className="text-xs text-purple-500 mt-2">IG Style: {formatEnumLabel(vd.style.instagram_style)}</p>
          )}
        </div>
      )}

      {/* Insights */}
      {vd.insights && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">💡 Insights</h4>
          <div className="space-y-2 text-xs text-gray-600 dark:text-gray-400">
            {vd.insights.engagement && (
              <div><span className="font-medium text-gray-700 dark:text-gray-300">Engagement:</span> {vd.insights.engagement}</div>
            )}
            {vd.insights.reverse_prompt && (
              <div><span className="font-medium text-gray-700 dark:text-gray-300">Prompt:</span> {vd.insights.reverse_prompt}</div>
            )}
            {vd.insights.brands?.length > 0 && (
              <div><span className="font-medium text-gray-700 dark:text-gray-300">Brands:</span> {vd.insights.brands.join(', ')}</div>
            )}
            {vd.insights.hashtags?.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1">
                {vd.insights.hashtags.map((h: string) => (
                  <span key={h} className="text-[10px] text-blue-500">{h}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── V2.0 Extended Tiers ── */}

      {/* Subjects */}
      {vd.subjects?.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">
            👤 Subjects ({vd.subjects.length})
          </h4>
          <div className="space-y-3">
            {vd.subjects.map((subj: any, i: number) => (
              <div key={i} className="border-l-2 border-rose-300 dark:border-rose-700 pl-3 space-y-1">
                <div className="text-xs text-gray-700 dark:text-gray-300 font-medium">
                  {formatSubjectIdentity(subj)}
                </div>
                {subj.body_type && (
                  <div className="text-xs text-gray-500">
                    Body: {formatBodyType(subj.body_type)}
                  </div>
                )}
                {(subj.skin_tone || subj.perceived_ethnicity || subj.face_shape) && (
                  <div className="text-xs text-gray-500">
                    {formatDemographics(subj)}
                  </div>
                )}
                {subj.facial_features && (
                  <div className="text-xs text-gray-500 italic">
                    {subj.facial_features}
                  </div>
                )}
                {subj.hair && (subj.hair.length || subj.hair.color || subj.hair.style || subj.hair.texture) && (
                  <div className="text-xs text-gray-500">
                    Hair: {formatHair(subj.hair)}
                  </div>
                )}
                {subj.clothing?.length > 0 && (
                  <div className="text-xs text-gray-500">
                    Clothing: {subj.clothing.map((c: any) => formatClothingItem(c)).filter(Boolean).join(', ')}
                  </div>
                )}
                {subj.coverage && formatCoverage(subj.coverage) && (
                  <div className="text-xs text-gray-500">
                    Coverage: {formatCoverage(subj.coverage)}
                  </div>
                )}
                {subj.negative_observations?.length > 0 && (
                  <div className="text-xs text-amber-600 dark:text-amber-300">
                    Negative Observations: {subj.negative_observations.map(formatEnumLabel).filter(Boolean).join(' | ')}
                  </div>
                )}
                {subj.accessories?.length > 0 && (
                  <div className="text-xs text-gray-500">Accessories: {subj.accessories.map(formatEnumLabel).filter(Boolean).join(', ')}</div>
                )}
                {subj.pose && (subj.pose.stance || subj.pose.gaze_direction || subj.pose.gesture || subj.pose.body_orientation) && (
                  <div className="text-xs text-gray-500">
                    Pose: {formatPose(subj.pose)}
                  </div>
                )}
                {subj.archetype_tags?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {subj.archetype_tags.map((t: string) => (
                      <span key={t} className="text-[10px] bg-pink-100 dark:bg-pink-900/30 text-pink-600 px-1.5 py-0.5 rounded">{formatEnumLabel(t)}</span>
                    ))}
                  </div>
                )}
                {subj.evidence_notes?.length > 0 && (
                  <div className="text-xs text-gray-500 italic">
                    Evidence: {formatEvidenceList(subj.evidence_notes)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Camera Tech */}
      {vd.camera_tech && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">📸 Camera Tech</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
            {vd.camera_tech.focal_length_class && (
              <div><span className="font-medium">Focal:</span> {formatEnumLabel(vd.camera_tech.focal_length_class)}{vd.camera_tech.focal_length_mm_range ? ` (${vd.camera_tech.focal_length_mm_range})` : ''}</div>
            )}
            {vd.camera_tech.depth_of_field && (
              <div><span className="font-medium">DoF:</span> {formatEnumLabel(vd.camera_tech.depth_of_field)}</div>
            )}
            {vd.camera_tech.estimated_aperture && (
              <div><span className="font-medium">Aperture:</span> {vd.camera_tech.estimated_aperture}</div>
            )}
            {vd.camera_tech.shot_type && (
              <div><span className="font-medium">Shot:</span> {formatEnumLabel(vd.camera_tech.shot_type)}</div>
            )}
            {vd.camera_tech.shutter_effect && (
              <div><span className="font-medium">Shutter:</span> {formatEnumLabel(vd.camera_tech.shutter_effect)}</div>
            )}
            {vd.camera_tech.camera_movement && (
              <div><span className="font-medium">Movement:</span> {formatEnumLabel(vd.camera_tech.camera_movement)}</div>
            )}
            {vd.camera_tech.aspect_ratio && (
              <div><span className="font-medium">Ratio:</span> {vd.camera_tech.aspect_ratio}</div>
            )}
          </div>
          {vd.camera_tech.framing && (
            <div className="flex flex-wrap gap-1 mt-2">
              {vd.camera_tech.framing.rule_of_thirds && (
                <span className="text-[10px] bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 px-1.5 py-0.5 rounded">✓ Rule of Thirds</span>
              )}
              {vd.camera_tech.framing.symmetry && (
                <span className="text-[10px] bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 px-1.5 py-0.5 rounded">✓ Symmetry</span>
              )}
              {vd.camera_tech.framing.leading_lines && (
                <span className="text-[10px] bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 px-1.5 py-0.5 rounded">✓ Leading Lines</span>
              )}
              {vd.camera_tech.framing.negative_space_ratio && (
                <span className="text-[10px] bg-cyan-100 dark:bg-cyan-900/30 text-cyan-600 px-1.5 py-0.5 rounded">Space: {vd.camera_tech.framing.negative_space_ratio}</span>
              )}
            </div>
          )}
          {vd.camera_tech.evidence_notes?.length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              Evidence: {formatEvidenceList(vd.camera_tech.evidence_notes)}
            </div>
          )}
        </div>
      )}

      {/* Environment */}
      {vd.environment && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">🌍 Environment</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400 mb-2">
            {vd.environment.location_type && (
              <div><span className="font-medium">Location:</span> {formatEnumLabel(vd.environment.location_type)}{vd.environment.location_subtype ? ` / ${formatEnumLabel(vd.environment.location_subtype)}` : ''}</div>
            )}
            {vd.environment.time_of_day && (
              <div><span className="font-medium">Time:</span> {formatEnumLabel(vd.environment.time_of_day)}</div>
            )}
            {vd.environment.weather_atmosphere && (
              <div><span className="font-medium">Weather:</span> {formatEnumLabel(vd.environment.weather_atmosphere)}</div>
            )}
          </div>
          {(vd.environment.foreground_elements?.length > 0 ||
            vd.environment.midground_elements?.length > 0 ||
            vd.environment.background_elements?.length > 0) && (
            <div className="space-y-1 text-xs">
              {vd.environment.foreground_elements?.length > 0 && (
                <div className="flex gap-1 items-center flex-wrap">
                  <span className="text-gray-500 font-medium w-8">FG:</span>
                  {vd.environment.foreground_elements.map((e: string) => (
                    <span key={e} className="text-[10px] bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 px-1.5 py-0.5 rounded">{formatEnumLabel(e)}</span>
                  ))}
                </div>
              )}
              {vd.environment.midground_elements?.length > 0 && (
                <div className="flex gap-1 items-center flex-wrap">
                  <span className="text-gray-500 font-medium w-8">MG:</span>
                  {vd.environment.midground_elements.map((e: string) => (
                    <span key={e} className="text-[10px] bg-teal-100 dark:bg-teal-900/30 text-teal-600 px-1.5 py-0.5 rounded">{formatEnumLabel(e)}</span>
                  ))}
                </div>
              )}
              {vd.environment.background_elements?.length > 0 && (
                <div className="flex gap-1 items-center flex-wrap">
                  <span className="text-gray-500 font-medium w-8">BG:</span>
                  {vd.environment.background_elements.map((e: string) => (
                    <span key={e} className="text-[10px] bg-green-100 dark:bg-green-900/30 text-green-600 px-1.5 py-0.5 rounded">{formatEnumLabel(e)}</span>
                  ))}
                </div>
              )}
            </div>
          )}
          {vd.environment.interactive_props?.length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              Props: {vd.environment.interactive_props.map((p: any) => formatPropItem(p)).filter(Boolean).join(', ')}
            </div>
          )}
          {vd.environment.set_dressing?.length > 0 && (
            <div className="text-xs text-gray-500 mt-1">
              Set Dressing: {vd.environment.set_dressing.map(formatEnumLabel).filter(Boolean).join(', ')}
            </div>
          )}
          {vd.environment.light_source?.source_type && (
            <div className="text-xs text-gray-500 mt-2">
              💡 Light: {formatLightSource(vd.environment.light_source)}
            </div>
          )}
          {vd.environment.evidence_notes?.length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              Evidence: {formatEvidenceList(vd.environment.evidence_notes)}
            </div>
          )}
        </div>
      )}

      {/* Material */}
      {vd.material?.materials?.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">🧱 Material</h4>
          <div className="flex flex-wrap gap-1">
            {vd.material.materials.map((m: any, i: number) => (
              <span key={i} className="text-[10px] bg-stone-100 dark:bg-stone-900/30 text-stone-600 px-1.5 py-0.5 rounded">
                {formatMaterialItem(m)}
              </span>
            ))}
          </div>
          {vd.material.texture_notes && (
            <p className="text-xs text-gray-500 mt-1 italic">{vd.material.texture_notes}</p>
          )}
        </div>
      )}

      {showProductInteraction && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">🛍️ Product Interaction</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
            {vd.product_interaction.product_visible && (
              <div><span className="font-medium">Product Visible:</span> yes</div>
            )}
            {vd.product_interaction.product_category && (
              <div><span className="font-medium">Category:</span> {formatEnumLabel(vd.product_interaction.product_category)}</div>
            )}
            {vd.product_interaction.interaction_type && (
              <div><span className="font-medium">Interaction:</span> {formatEnumLabel(vd.product_interaction.interaction_type)}</div>
            )}
            {vd.product_interaction.placement_region && (
              <div><span className="font-medium">Placement:</span> {formatEnumLabel(vd.product_interaction.placement_region)}</div>
            )}
            {vd.product_interaction.brand_visible && (
              <div><span className="font-medium">Brand Visible:</span> yes</div>
            )}
          </div>
        </div>
      )}

      {showSafetyFlags && (
        <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-500 mb-2">⚠️ Safety</h4>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
            {vd.safety_flags.nsfw_risk && vd.safety_flags.nsfw_risk !== 'none' && (
              <div><span className="font-medium">NSFW Risk:</span> {formatEnumLabel(vd.safety_flags.nsfw_risk)}</div>
            )}
            {vd.safety_flags.medical_claims && (
              <div><span className="font-medium">Medical Claims:</span> yes</div>
            )}
          </div>
          {vd.safety_flags.copyright_concerns && (
            <p className="text-xs text-gray-500 mt-2">{vd.safety_flags.copyright_concerns}</p>
          )}
        </div>
      )}
        </>
      )}

      {activeTab === 'annotations' && hasAnnotations && (
        <div className="space-y-3">
          <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
            <div className="flex flex-wrap items-center gap-2">
              {trainingAnnotations.training_readiness && (
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full ${
                    trainingAnnotations.training_readiness === 'keep'
                      ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                      : trainingAnnotations.training_readiness === 'review'
                        ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                        : 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300'
                  }`}
                >
                  {formatEnumLabel(trainingAnnotations.training_readiness)}
                </span>
              )}
              {trainingAnnotations.dataset_mix_role && (
                <span className="text-[10px] bg-slate-100 dark:bg-slate-900/30 text-slate-700 dark:text-slate-300 px-1.5 py-0.5 rounded">
                  {formatEnumLabel(trainingAnnotations.dataset_mix_role)}
                </span>
              )}
              {trainingAnnotations.identity_signal_strength && (
                <span className="text-[10px] bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1.5 py-0.5 rounded">
                  signal {formatEnumLabel(trainingAnnotations.identity_signal_strength)}
                </span>
              )}
              {trainingAnnotations.training_source_kind && (
                <span className="text-[10px] bg-stone-100 dark:bg-stone-900/30 text-stone-700 dark:text-stone-300 px-1.5 py-0.5 rounded">
                  {formatEnumLabel(trainingAnnotations.training_source_kind)}
                </span>
              )}
              {trainingAnnotations.training_lane_hints?.map((lane: string) => (
                <span key={lane} className="text-[10px] bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 px-1.5 py-0.5 rounded">
                  {formatEnumLabel(lane)}
                </span>
              ))}
            </div>
            {trainingAnnotations.training_notes && (
              <p className="text-xs text-gray-600 dark:text-gray-300 mt-3">
                {trainingAnnotations.training_notes}
              </p>
            )}
          </div>

          <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
            <h4 className="text-xs font-semibold text-gray-500 mb-2">Dataset Fit</h4>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
              {trainingAnnotations.subject_framing && (
                <div><span className="font-medium">Framing:</span> {formatEnumLabel(trainingAnnotations.subject_framing)}</div>
              )}
              {trainingAnnotations.face_angle && (
                <div><span className="font-medium">Face Angle:</span> {formatEnumLabel(trainingAnnotations.face_angle)}</div>
              )}
              {trainingAnnotations.face_visibility && (
                <div><span className="font-medium">Face Visibility:</span> {formatEnumLabel(trainingAnnotations.face_visibility)}</div>
              )}
              {trainingAnnotations.occlusion_level && (
                <div><span className="font-medium">Occlusion:</span> {formatEnumLabel(trainingAnnotations.occlusion_level)}</div>
              )}
              {trainingAnnotations.style_strength && (
                <div><span className="font-medium">Style Strength:</span> {formatEnumLabel(trainingAnnotations.style_strength)}</div>
              )}
              {trainingAnnotations.identity_drift_risk && (
                <div><span className="font-medium">Identity Drift Risk:</span> {formatEnumLabel(trainingAnnotations.identity_drift_risk)}</div>
              )}
              {trainingAnnotations.look_variant_level && (
                <div><span className="font-medium">Look Variant Level:</span> {formatEnumLabel(trainingAnnotations.look_variant_level)}</div>
              )}
              {trainingAnnotations.primary_subject_clarity && (
                <div><span className="font-medium">Primary Subject:</span> {formatEnumLabel(trainingAnnotations.primary_subject_clarity)}</div>
              )}
            </div>
          </div>

          {trainingAnnotations.style_tags?.length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-gray-500 mb-2">Style Tags</h4>
              <div className="flex flex-wrap gap-1">
                {trainingAnnotations.style_tags.map((tag: string) => (
                  <span key={tag} className="text-[10px] bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300 px-1.5 py-0.5 rounded">
                    {formatEnumLabel(tag)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {trainingAnnotations.quality_flags?.length > 0 && (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-gray-500 mb-2">Quality Flags</h4>
              <div className="flex flex-wrap gap-1">
                {trainingAnnotations.quality_flags.map((flag: string) => (
                  <span key={flag} className="text-[10px] bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 px-1.5 py-0.5 rounded">
                    {formatEnumLabel(flag)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {trainingAnnotations.hard_blockers?.length > 0 && (
            <div className="bg-red-50 dark:bg-red-950/20 rounded-lg border border-red-200 dark:border-red-800/40 p-3">
              <h4 className="text-xs font-semibold text-red-700 dark:text-red-300 mb-2">Hard Blockers</h4>
              <div className="flex flex-wrap gap-1">
                {trainingAnnotations.hard_blockers.map((flag: string) => (
                  <span key={flag} className="text-[10px] bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-1.5 py-0.5 rounded">
                    {formatEnumLabel(flag)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(trainingAnnotations.identity_cluster_hint || trainingAnnotations.look_state_hint) && (
            <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
              <h4 className="text-xs font-semibold text-gray-500 mb-2">Grouping Hints</h4>
              <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                {trainingAnnotations.identity_cluster_hint && (
                  <div><span className="font-medium">Identity Cluster:</span> {trainingAnnotations.identity_cluster_hint}</div>
                )}
                {trainingAnnotations.look_state_hint && (
                  <div><span className="font-medium">Look State:</span> {trainingAnnotations.look_state_hint}</div>
                )}
              </div>
            </div>
          )}

          {trainingAnnotations.reject_reasons?.length > 0 && (
            <div className="bg-rose-50 dark:bg-rose-950/20 rounded-lg border border-rose-200 dark:border-rose-800/40 p-3">
              <h4 className="text-xs font-semibold text-rose-700 dark:text-rose-300 mb-2">Reject Reasons</h4>
              <div className="flex flex-wrap gap-1">
                {trainingAnnotations.reject_reasons.map((reason: string) => (
                  <span key={reason} className="text-[10px] bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300 px-1.5 py-0.5 rounded">
                    {formatEnumLabel(reason)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'annotations' && !hasAnnotations && (
        <div className="rounded-lg border border-dashed border-gray-200 dark:border-gray-700 p-3 text-xs text-gray-500 dark:text-gray-400">
          No training annotations were captured for this reference.
        </div>
      )}

      {activeTab === 'thinking' && hasThinking && (
        <div className="bg-violet-50 dark:bg-violet-950/30 rounded-lg border border-violet-200 dark:border-violet-800/50 p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-violet-700 dark:text-violet-300">
            <span>🧠 Thinking</span>
            <span className="text-[10px] font-normal text-violet-500 dark:text-violet-400">
              {thinkingText.length.toLocaleString()} chars
            </span>
          </div>
          <pre className="text-[11px] text-violet-800 dark:text-violet-200 whitespace-pre-wrap font-mono leading-relaxed max-h-[28rem] overflow-y-auto">
            {thinkingText}
          </pre>
        </div>
      )}

      {activeTab === 'thinking' && !hasThinking && (
        <div className="rounded-lg border border-dashed border-violet-200 dark:border-violet-800/50 p-3 text-xs text-violet-700 dark:text-violet-300">
          No thinking trace was captured for this reference.
        </div>
      )}

      {activeTab === 'raw' && hasRaw && (
        <div className="bg-amber-50 dark:bg-amber-950/20 rounded-lg border border-amber-200 dark:border-amber-800/50 p-3 space-y-3">
          {(failureStage || failureReason) && (
            <div className="space-y-1 text-xs text-amber-800 dark:text-amber-200">
              {failureStage && (
                <div>
                  <span className="font-semibold">Stage:</span> {failureStage}
                </div>
              )}
              {failureReason && (
                <div>
                  <span className="font-semibold">Reason:</span> {failureReason}
                </div>
              )}
            </div>
          )}
          {rawText ? (
            <pre className="text-[11px] text-amber-900 dark:text-amber-100 whitespace-pre-wrap font-mono leading-relaxed max-h-[28rem] overflow-y-auto">
              {rawText}
            </pre>
          ) : (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              No raw model output was captured for this run.
            </p>
          )}
        </div>
      )}

      {activeTab === 'raw' && !hasRaw && (
        <div className="rounded-lg border border-dashed border-amber-200 dark:border-amber-800/50 p-3 text-xs text-amber-700 dark:text-amber-300">
          No raw model output was captured for this reference.
        </div>
      )}
    </div>
  );
}
