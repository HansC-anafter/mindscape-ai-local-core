'use client';

import React, { useState } from 'react';
import { DeployRequest, DeployResponse, deployProject } from '@/lib/deployment-api';
import DeployStep1Target from './DeployStep1Target';
import DeployStep2Git from './DeployStep2Git';
import DeployStep3Execute from './DeployStep3Execute';
import DeployStep4Result from './DeployStep4Result';

interface DeployModalProps {
  workspaceId: string;
  projectId: string;
  sandboxId: string;
  isOpen: boolean;
  onClose: () => void;
}

type DeployStep = 1 | 2 | 3 | 4;

export default function DeployModal({
  workspaceId,
  projectId,
  sandboxId,
  isOpen,
  onClose,
}: DeployModalProps) {
  const [currentStep, setCurrentStep] = useState<DeployStep>(1);
  const [deployConfig, setDeployConfig] = useState<Partial<DeployRequest>>({
    sandbox_id: sandboxId,
    target_path: '',
    git_branch: '',
    commit_message: '',
    auto_commit: false,
    auto_push: false,
  });
  const [deployResult, setDeployResult] = useState<DeployResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleNext = () => {
    if (currentStep < 4) {
      setCurrentStep((currentStep + 1) as DeployStep);
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep((currentStep - 1) as DeployStep);
    }
  };

  const handleDeploy = async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await deployProject(workspaceId, projectId, deployConfig as DeployRequest);
      setDeployResult(result);
      setCurrentStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deployment failed');
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setCurrentStep(1);
    setDeployConfig({
      sandbox_id: sandboxId,
      target_path: '',
      git_branch: '',
      commit_message: '',
      auto_commit: false,
      auto_push: false,
    });
    setDeployResult(null);
    setError(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold">Deploy Project</h2>
            <button
              onClick={handleClose}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          </div>

          <div className="mb-6">
            <div className="flex items-center justify-between">
              {[1, 2, 3, 4].map((step) => (
                <div key={step} className="flex items-center flex-1">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      currentStep >= step
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-200 text-gray-600'
                    }`}
                  >
                    {step}
                  </div>
                  {step < 4 && (
                    <div
                      className={`flex-1 h-1 mx-2 ${
                        currentStep > step ? 'bg-blue-600' : 'bg-gray-200'
                      }`}
                    />
                  )}
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-2 text-xs text-gray-500">
              <span>Target</span>
              <span>Git Config</span>
              <span>Execute</span>
              <span>Result</span>
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
              {error}
            </div>
          )}

          {currentStep === 1 && (
            <DeployStep1Target
              config={deployConfig}
              onUpdate={(updates) => setDeployConfig({ ...deployConfig, ...updates })}
              onNext={handleNext}
            />
          )}

          {currentStep === 2 && (
            <DeployStep2Git
              config={deployConfig}
              onUpdate={(updates) => setDeployConfig({ ...deployConfig, ...updates })}
              onNext={handleNext}
              onBack={handleBack}
            />
          )}

          {currentStep === 3 && (
            <DeployStep3Execute
              config={deployConfig}
              onDeploy={handleDeploy}
              onBack={handleBack}
              loading={loading}
            />
          )}

          {currentStep === 4 && (
            <DeployStep4Result
              result={deployResult}
              onClose={handleClose}
            />
          )}
        </div>
      </div>
    </div>
  );
}

