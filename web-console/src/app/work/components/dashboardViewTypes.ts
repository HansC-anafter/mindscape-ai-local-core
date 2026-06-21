export type DashboardTab = 'inbox' | 'cases' | 'assignments';
export type DashboardSelectedItemType = 'inbox' | 'case' | 'assignment';

export interface DashboardSelectedItem {
    type: DashboardSelectedItemType;
    id: string;
    data: any;
}
