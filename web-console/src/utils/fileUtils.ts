import type { UploadedFile } from '@/hooks/useFileUpload';

export function isFileDuplicate(
  file: File,
  uploadedFiles: UploadedFile[]
): boolean {
  return uploadedFiles.some(
    uploadedFile => uploadedFile.name === file.name && uploadedFile.size === file.size
  );
}

export function revokeFilePreviewURLs(files: UploadedFile[]): void {
  files.forEach(file => {
    if (file.preview) {
      URL.revokeObjectURL(file.preview);
    }
  });
}

export function createFilePreviewURL(file: File): string | null {
  if (file.type.startsWith('image/')) {
    return URL.createObjectURL(file);
  }
  return null;
}
