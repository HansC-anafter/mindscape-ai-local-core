/**
 * Common types for playbook view components
 */

export interface ViewItem {
  id: string;
  title: string;
  [key: string]: any;
}

export interface BinderViewProps<T extends ViewItem> {
  items: T[];
  selectedId?: string | null;
  onSelect?: (item: T) => void;
  onReorder?: (items: T[]) => void;
  renderItem?: (item: T, isSelected: boolean) => React.ReactNode;
  getItemIcon?: (item: T) => React.ReactNode;
  getItemStatus?: (item: T) => string;
  allowReorder?: boolean;
}

export interface CorkboardViewProps<T extends ViewItem> {
  items: T[];
  selectedId?: string | null;
  onSelect?: (item: T) => void;
  onReorder?: (items: T[]) => void;
  renderCard?: (item: T, isSelected: boolean) => React.ReactNode;
  getCardStatus?: (item: T) => string;
  allowReorder?: boolean;
  columns?: number;
}

export interface OutlinerViewProps<T extends ViewItem> {
  items: T[];
  selectedId?: string | null;
  onSelect?: (item: T) => void;
  onReorder?: (items: T[]) => void;
  columns: Array<{
    key: string;
    label: string;
    render?: (item: T) => React.ReactNode;
    width?: string;
  }>;
  allowReorder?: boolean;
}

