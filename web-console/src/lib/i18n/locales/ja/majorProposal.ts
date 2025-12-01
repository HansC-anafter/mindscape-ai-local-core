/**
 * Major Proposal i18n messages (Japanese)
 * Major proposal errors and UI strings
 */
import type { MessageKey } from '../../keys';

export const majorProposalJa = {
  // Major Proposal errors
  majorProposalDraftGenerated: '章の草稿が生成されました！',
  majorProposalGenerateFailed: '生成に失敗しました：{error}',
  majorProposalAssembleFailed: '組み立てに失敗しました：{error}',
  majorProposalAssembled: 'ファイルの組み立てが完了しました！\n\nMarkdown コンテンツが生成されました。\nDOCX ファイルパス: {path}',
  majorProposalEnterContent: '少なくとも何かコンテンツを入力してください',
  majorProposalSaved: '保存済み',
  majorProposalSaveFailed: '保存に失敗しました：{error}',
  majorProposalSelectTemplate: 'テンプレートを選択してください',
  majorProposalEnterProjectName: 'プロジェクト名を入力してください',
  majorProposalCreateProjectFailed: 'プロジェクトの作成に失敗しました：{error}',
  majorProposalTemplateCreated: 'テンプレートが正常に作成されました！ID: {id}',
  majorProposalUploadFailed: 'アップロードに失敗しました：{error}',
  majorProposalSelectAtLeastOneFile: '少なくとも 1 つのファイルを選択してください',
  majorProposalProjectNotFound: 'プロジェクトが見つかりません',
  majorProposalTemplateNotFound: 'テンプレートが見つかりません',
  majorProposalAssembling: '組み立て中...',
  majorProposalAssembleComplete: '完全なファイルを組み立て',
  majorProposalGenerating: '生成中...',
  majorProposalGenerateDraft: '章の草稿を生成',
  majorProposalSaving: '保存中...',
  majorProposalSaveEdit: '編集を保存',
  majorProposalEnterInfo: '関連情報を入力してください...',
  majorProposalEnterProjectNamePlaceholder: '例：私のスタートアップ助成金申請',
  majorProposalCreating: '作成中...',
  majorProposalCreateProject: 'プロジェクトを作成',
  majorProposalUploading: 'アップロード中...',
  majorProposalUpload: 'アップロード',
  majorProposalEnterTemplateNamePlaceholder: '例：2025 年度スタートアップ助成金申請',
  majorProposalWordLimit: '文字数制限: {min} - {max} 文字',
  majorProposalNoWordLimit: '文字数制限: {min} - 上限なし 文字',
} as const satisfies Partial<Record<MessageKey, string>>;

