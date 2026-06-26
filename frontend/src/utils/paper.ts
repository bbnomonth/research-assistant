import type { Paper } from '@/types/api';

export function parseAuthors(paper: Paper): string[] {
  try {
    const value = JSON.parse(paper.authors_json || '[]');
    return Array.isArray(value) ? (value as string[]) : [];
  } catch {
    return [];
  }
}

export function parseCategories(paper: Paper): string[] {
  try {
    const value = JSON.parse(paper.categories_json || '[]');
    return Array.isArray(value) ? (value as string[]) : [];
  } catch {
    return [];
  }
}

export function parsePurposeLabels(paper: Paper): string[] {
  try {
    const value = JSON.parse(paper.purpose_labels_json || '[]');
    return Array.isArray(value) ? (value as string[]) : [];
  } catch {
    return [];
  }
}

export function shortAuthors(authors: string[]): string {
  if (authors.length <= 3) return authors.join(', ');
  return `${authors.slice(0, 3).join(', ')} 等`;
}

export function isUploaded(paper: Paper): boolean {
  return paper.arxiv_id.startsWith('upload:');
}
