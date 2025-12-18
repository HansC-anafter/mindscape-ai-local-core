import type { UploadedFile } from '@/hooks/useFileUpload';

/**
 * Check if file is duplicate in uploaded files list.
 *
 * @param file - File to check
 * @param uploadedFiles - Array of uploaded files
 * @returns True if file is duplicate
 */
export function isFileDuplicate(
  file: File,
  uploadedFiles: UploadedFile[]
): boolean {
  return uploadedFiles.some(
    uploadedFile => uploadedFile.name === file.name && uploadedFile.size === file.size
  );
}

/**
 * Revoke object URLs for uploaded files.
 *
 * @param files - Array of uploaded files
 */
export function revokeFilePreviewURLs(files: UploadedFile[]): void {
  files.forEach(file => {
    if (file.preview) {
      URL.revokeObjectURL(file.preview);
    }
  });
}

/**
 * Create preview URL for file.
 *
 * @param file - File to create preview for
 * @returns Preview URL or null if not supported
 */
export function createFilePreviewURL(file: File): string | null {
  if (file.type.startsWith('image/')) {
    return URL.createObjectURL(file);
  }
  return null;
}

