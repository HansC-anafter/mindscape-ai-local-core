'use client';

/**
 * Ready Score Component
 *
 * Features:
 * - Real-time Ready Score display
 * - Missing items indication
 * - Improvement recommendations
 */

import React, { useState, useEffect } from 'react';
import { CheckCircle2, XCircle, AlertCircle, TrendingUp, Info } from 'lucide-react';
import type { IGPost } from './types';

interface ReadyScoreProps {
  post: IGPost | null;
  apiUrl: string;
  workspaceId: string;
}

interface ReadinessCheck {
  field: string;
  label: string;
  status: 'pass' | 'fail' | 'warning';
  message?: string;
  required: boolean;
}

interface ReadinessResult {
  score: number; // 0-100
  checks: ReadinessCheck[];
  missing_fields: string[];
  recommendations: string[];
}

export default function ReadyScore({
  post,
  apiUrl,
  workspaceId
}: ReadyScoreProps) {
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (post) {
      calculateReadiness();
    } else {
      setReadiness(null);
    }
  }, [post]);

  const calculateReadiness = async () => {
    if (!post || !post.post_path) {
      setReadiness(null);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/playbooks/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook_code: 'ig_frontmatter_validator',
          inputs: {
            workspace_id: workspaceId,
            post_path: post.post_path || post.artifact_id
          },
          execution_mode: 'sync'
        }),
      });

      if (response.ok) {
        const data = await response.json();
        const validationResult = data.result?.validation_result || {};
        const checks = data.result?.checks || [];

        const readinessResult: ReadinessResult = {
          score: calculateScore(checks),
          checks: checks.map((check: any) => ({
            field: check.field,
            label: getFieldLabel(check.field),
            status: check.valid ? 'pass' : (check.required ? 'fail' : 'warning'),
            message: check.message,
            required: check.required || false
          })),
          missing_fields: checks.filter((c: any) => !c.valid && c.required).map((c: any) => c.field),
          recommendations: generateRecommendations(checks)
        };

        setReadiness(readinessResult);
      } else {
        setReadiness(calculateLocalReadiness(post));
      }
    } catch (err) {
      console.error('Failed to calculate readiness:', err);
      setReadiness(calculateLocalReadiness(post));
    } finally {
      setLoading(false);
    }
  };

  const calculateScore = (checks: any[]): number => {
    if (checks.length === 0) return 0;
    const passed = checks.filter((c: any) => c.valid).length;
    return Math.round((passed / checks.length) * 100);
  };

  const getFieldLabel = (field: string): string => {
    const labels: Record<string, string> = {
      'media_path': 'Media File',
      'caption': 'Caption/Description',
      'hashtags': 'Hashtags',
      'series_id': 'Series ID',
      'scheduled_time': 'Scheduled Time',
      'channel_config_id': 'Publish Account',
      'metadata': 'Metadata',
      'frontmatter': 'Frontmatter'
    };
    return labels[field] || field;
  };

  const generateRecommendations = (checks: any[]): string[] => {
    const recommendations: string[] = [];
    const failedChecks = checks.filter((c: any) => !c.valid && c.required);

    failedChecks.forEach((check: any) => {
      switch (check.field) {
        case 'media_path':
          recommendations.push('Add media file path (media_path)');
          break;
        case 'caption':
          recommendations.push('Add post title or description (caption)');
          break;
        case 'hashtags':
          recommendations.push('Consider adding Hashtags to improve visibility');
          break;
        case 'channel_config_id':
          recommendations.push('Select publish account (channel_config_id)');
          break;
        case 'scheduled_time':
          recommendations.push('Set scheduled_time if scheduling publish');
          break;
        default:
          if (check.message) {
            recommendations.push(check.message);
          }
      }
    });

    return recommendations;
  };

  const calculateLocalReadiness = (post: IGPost): ReadinessResult => {
    const checks: ReadinessCheck[] = [
      {
        field: 'media_path',
        label: 'Media File',
        status: post.frontmatter?.media_path ? 'pass' : 'fail',
        message: post.frontmatter?.media_path ? undefined : 'Missing media file path',
        required: true
      },
      {
        field: 'caption',
        label: 'Caption/Description',
        status: (post.frontmatter?.caption || post.content || post.text) ? 'pass' : 'fail',
        message: (post.frontmatter?.caption || post.content || post.text) ? undefined : 'Missing caption or description',
        required: true
      },
      {
        field: 'hashtags',
        label: 'Hashtags',
        status: post.hashtags && post.hashtags.length > 0 ? 'pass' : 'warning',
        message: post.hashtags && post.hashtags.length > 0 ? undefined : 'Consider adding Hashtags',
        required: false
      },
      {
        field: 'channel_config_id',
        label: 'Publish Account',
        status: post.frontmatter?.channel_config_id ? 'pass' : 'warning',
        message: post.frontmatter?.channel_config_id ? undefined : 'Account selection required for publish',
        required: false
      }
    ];

    const passed = checks.filter(c => c.status === 'pass').length;
    const score = Math.round((passed / checks.length) * 100);
    const missing_fields = checks.filter(c => c.status === 'fail' && c.required).map(c => c.field);
    const recommendations = generateRecommendations(checks.map(c => ({
      field: c.field,
      valid: c.status === 'pass',
      required: c.required,
      message: c.message
    })));

    return {
      score,
      checks,
      missing_fields,
      recommendations
    };
  };

  const getScoreColor = (score: number): string => {
    if (score >= 80) return 'text-green-600 dark:text-green-400';
    if (score >= 60) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  const getScoreBgColor = (score: number): string => {
    if (score >= 80) return 'bg-green-100 dark:bg-green-900/20';
    if (score >= 60) return 'bg-yellow-100 dark:bg-yellow-900/20';
    return 'bg-red-100 dark:bg-red-900/20';
  };

  if (!post) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Ready Score
          </h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Please select a post first
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Ready Score
          </h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Calculating...
        </p>
      </div>
    );
  }

  if (!readiness) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Ready Score
          </h3>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Unable to calculate readiness score
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Ready Score
          </h3>
        </div>
        <div className={`px-3 py-1 rounded-lg ${getScoreBgColor(readiness.score)}`}>
          <span className={`text-lg font-bold ${getScoreColor(readiness.score)}`}>
            {readiness.score}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">/100</span>
        </div>
      </div>

      {/* Check items list */}
      <div className="space-y-2 mb-3">
        {readiness.checks.map((check, index) => (
          <div
            key={index}
            className="flex items-start gap-2 text-xs"
          >
            {check.status === 'pass' ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" />
            ) : check.status === 'fail' ? (
              <XCircle className="w-3.5 h-3.5 text-red-500 mt-0.5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 text-yellow-500 mt-0.5 flex-shrink-0" />
            )}
            <div className="flex-1">
              <span className={`${
                check.status === 'pass' ? 'text-green-700 dark:text-green-300' :
                check.status === 'fail' ? 'text-red-700 dark:text-red-300' :
                'text-yellow-700 dark:text-yellow-300'
              }`}>
                {check.label}
              </span>
              {check.message && (
                <span className="text-gray-500 dark:text-gray-400 ml-1">
                  - {check.message}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Missing required fields */}
      {readiness.missing_fields.length > 0 && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-2 mb-3">
          <div className="flex items-start gap-2">
            <AlertCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400 mt-0.5" />
            <div className="flex-1">
              <p className="text-xs font-semibold text-red-900 dark:text-red-100 mb-1">
                Missing Required Fields
              </p>
              <ul className="text-xs text-red-700 dark:text-red-300 space-y-0.5">
                {readiness.missing_fields.map((field, index) => (
                  <li key={index}>• {getFieldLabel(field)}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Improvement recommendations */}
      {readiness.recommendations.length > 0 && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-2">
          <div className="flex items-start gap-2">
            <Info className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 mt-0.5" />
            <div className="flex-1">
              <p className="text-xs font-semibold text-blue-900 dark:text-blue-100 mb-1">
                Recommendations
              </p>
              <ul className="text-xs text-blue-700 dark:text-blue-300 space-y-0.5">
                {readiness.recommendations.map((rec, index) => (
                  <li key={index}>• {rec}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
