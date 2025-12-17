import type { PlaybookStepDefinition } from '../types/execution';

/**
 * Parse playbook steps from various data structures
 */
export function parsePlaybookSteps(data: any): PlaybookStepDefinition[] {
  const stepDefs: PlaybookStepDefinition[] = [];
  let playbookSteps: any[] = [];

  // First, try direct steps array in metadata or root
  if (Array.isArray(data.steps) && data.steps.length > 0) {
    playbookSteps = data.steps;
  } else if (data.metadata?.steps && Array.isArray(data.metadata.steps) && data.metadata.steps.length > 0) {
    playbookSteps = data.metadata.steps;
  } else if (data.workflow?.steps && Array.isArray(data.workflow.steps) && data.workflow.steps.length > 0) {
    playbookSteps = data.workflow.steps;
  } else if (data.sop_content) {
    const sopStr = typeof data.sop_content === 'string' ? data.sop_content.trim() : String(data.sop_content);
    if (sopStr.startsWith('{') || sopStr.startsWith('[')) {
      try {
        const parsed = JSON.parse(sopStr);
        if (parsed.steps && Array.isArray(parsed.steps) && parsed.steps.length > 0) {
          playbookSteps = parsed.steps;
        }
      } catch (e) {
        // sop_content is not JSON, try Markdown parsing
        playbookSteps = parseMarkdownSteps(sopStr);
      }
    } else {
      // sop_content is Markdown or other text format
      playbookSteps = parseMarkdownSteps(sopStr);
    }
  }

  // If still no steps found, try alternative fields
  if (playbookSteps.length === 0) {
    if (data.definition?.steps && Array.isArray(data.definition.steps)) {
      playbookSteps = data.definition.steps;
    } else if (data.content?.steps && Array.isArray(data.content.steps)) {
      playbookSteps = data.content.steps;
    }
  }

  // Extract step information from playbook structure
  playbookSteps.forEach((step: any, index: number) => {
    let description = '';
    if (step.inputs?.text) {
      const textParts = step.inputs.text.split('\n\n').map((p: string) => p.trim()).filter((p: string) => p);
      for (let i = textParts.length - 1; i >= 0; i--) {
        const part = textParts[i];
        if (part && !part.includes('{{') && part.length > 10) {
          description = part;
          break;
        }
      }
      if (!description && textParts.length > 0) {
        description = textParts[textParts.length - 1];
      }
    }

    const stepName = step.step_name
      ? step.step_name
      : (step.name
        ? step.name
        : (step.id && !step.id.startsWith('step_')
          ? step.id.split('_').map((word: string) =>
              word.charAt(0).toUpperCase() + word.slice(1)
            ).join(' ')
          : (step.title || `Step ${index + 1}`)));

    stepDefs.push({
      step_index: index + 1,
      step_name: stepName,
      description: description || step.description || step.instructions || step.prompt || '',
      agent_type: step.agent_type || step.agent,
      used_tools: step.tool ? [step.tool] : (step.tools || step.used_tools || [])
    });
  });

  return stepDefs;
}

/**
 * Parse steps from Markdown content
 */
function parseMarkdownSteps(sopStr: string): any[] {
  const stepPatterns = [
    /^##+\s+Step\s+(\d+)(?!\.\d)[:：]?\s*(.+)$/gmi,
    /^##+\s*步驟\s*(\d+)(?!\.\d)[:：]?\s*(.+)$/gmi,
    /^###\s+Step\s+(\d+)(?!\.\d)[:：]?\s*(.+)$/gmi,
    /^(\d+)\.\s+Step\s+(\d+)[:：]?\s*(.+)$/gmi,
    /^(\d+)\.\s*步驟\s*(\d+)[:：]?\s*(.+)$/gmi,
    /^-\s+Step\s+(\d+)[:：]?\s*(.+)$/gmi,
    /^Step\s+(\d+)(?!\.\d)[:：]?\s*(.+)$/gmi,
    /^步驟\s+(\d+)(?!\.\d)[:：]?\s*(.+)$/gmi,
    /^##+\s+(\d+)\.\s*(.+)$/gmi,
    /^##+\s+(.+)$/gmi,
    /^[1-9]\d*\.\s+(.+)$/gmi
  ];

  const extractedSteps: Array<{ step_index: number; step_name: string; description?: string }> = [];
  const lines = sopStr.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('.')) continue;

    if (/^####\s+Step\s+\d+\.\d+[:：]/.test(line)) continue;

    for (let pIdx = 0; pIdx < stepPatterns.length; pIdx++) {
      const pattern = stepPatterns[pIdx];
      pattern.lastIndex = 0;
      const match = pattern.exec(line);
      if (match) {
        if (line.startsWith('.')) continue;

        if (pIdx === 9) {
          const title = match[1] || match[2] || '';
          if (/^(Goal|Execution Steps|Personalization|Integration|Success Criteria|Notes|Related Documentation)$/i.test(title)) {
            continue;
          }
          const phaseMatch = title.match(/^Phase\s+(\d+)[:：]?\s*(.+)$/i);
          if (phaseMatch) {
            const phaseNumber = parseInt(phaseMatch[1], 10);
            const phaseName = phaseMatch[2] || title;
            let description = '';
            for (let j = i + 1; j < Math.min(i + 50, lines.length); j++) {
              const nextLine = lines[j].trim();
              if (nextLine.match(/^###\s+Phase\s+\d+/i) ||
                  (nextLine.match(/^##+/) && !nextLine.match(/^####/))) {
                break;
              }
              if (nextLine && !nextLine.match(/^####/)) {
                description += (description ? ' ' : '') + nextLine;
                if (description.length > 200) {
                  description = description.substring(0, 200) + '...';
                  break;
                }
              }
            }
            extractedSteps.push({
              step_index: phaseNumber,
              step_name: phaseName.trim() || `Phase ${phaseNumber}`,
              description: description.trim()
            });
            continue;
          }
        }

        const stepIndex = parseInt(match[1] || match[2] || '0', 10);
        if (line.startsWith('.')) continue;

        let stepName = '';
        if (match.length >= 4 && match[3]) {
          stepName = match[3];
        } else if (match.length >= 3 && match[2]) {
          if (/^\d+$/.test(match[2])) {
            stepName = match[3] || `Step ${stepIndex}`;
          } else {
            stepName = match[2];
          }
        } else {
          stepName = `Step ${stepIndex}`;
        }

        if (stepIndex > 0) {
          let description = '';
          for (let j = i + 1; j < Math.min(i + 20, lines.length); j++) {
            const nextLine = lines[j].trim();
            if (nextLine.match(/^##+\s+(Step|步驟|Step|步驟)\s+\d+/i) ||
                nextLine.match(/^(\d+)\.\s+(Step|步驟)\s+\d+/i) ||
                (nextLine.match(/^##+/) && !nextLine.match(/^\.\d+/))) {
              break;
            }
            if (nextLine && (nextLine.match(/^\.\d+[:：]/) || !nextLine.match(/^##+|^###+/))) {
              description += (description ? ' ' : '') + nextLine;
            }
          }
          extractedSteps.push({
            step_index: stepIndex,
            step_name: stepName.trim() || `Step ${stepIndex}`,
            description: description.trim()
          });
          break;
        }
      }
    }
  }

  if (extractedSteps.length > 0) {
    return extractedSteps.map((step, index) => ({
      id: `step_${index + 1}`,
      name: step.step_name,
      step_name: step.step_name,
      description: step.description,
      step_index: index + 1
    }));
  }

  return [];
}
