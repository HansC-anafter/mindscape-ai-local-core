import React from 'react';

import type { Analysis } from '../types';
import { getPerformanceBgColor, getPerformanceColor } from '../utils';

export function MeasureAnalysisPanel(props: { analysis: Analysis }) {
  const { analysis } = props;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
        Data Analysis
      </h3>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-700 dark:text-gray-300">Overall Performance</span>
          <span className={`px-3 py-1 rounded text-sm font-medium ${getPerformanceBgColor(analysis.overall_performance)} ${getPerformanceColor(analysis.overall_performance)}`}>
            {analysis.overall_performance === 'high' ? 'Excellent' :
             analysis.overall_performance === 'medium' ? 'Good' :
             'Needs Improvement'}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-700 dark:text-gray-300">Threshold Met</span>
          <span className={`px-3 py-1 rounded text-sm ${analysis.threshold_met ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400' : 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'}`}>
            {analysis.threshold_met ? 'Met' : 'Not Met'}
          </span>
        </div>

        {analysis.performance_elements && analysis.performance_elements.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Performance Elements
            </h4>
            <div className="space-y-2">
              {analysis.performance_elements.map((element, index) => (
                <div
                  key={index}
                  className="p-2 bg-gray-50 dark:bg-gray-700 rounded flex items-center justify-between"
                >
                  <div>
                    <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                      {element.element_type === 'hashtag' ? 'Hashtag' :
                       element.element_type === 'caption' ? 'Caption' :
                       element.element_type === 'image' ? 'Image' :
                       element.element_type === 'timing' ? 'Timing' :
                       'Series'}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                      {element.element_value}
                    </span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-xs ${getPerformanceBgColor(element.performance_level)} ${getPerformanceColor(element.performance_level)}`}>
                    {element.performance_level === 'high' ? 'High' :
                     element.performance_level === 'medium' ? 'Medium' :
                     'Low'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {analysis.recommendations && analysis.recommendations.length > 0 && (
          <div className="mt-4">
            <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Recommendations
            </h4>
            <ul className="space-y-1">
              {analysis.recommendations.map((rec, index) => (
                <li key={index} className="text-xs text-gray-600 dark:text-gray-300 flex items-start gap-2">
                  <span className="text-blue-500 mt-0.5">•</span>
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

