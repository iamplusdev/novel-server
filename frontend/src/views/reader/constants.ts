/** 阅读器共享类型与字体常量 */
export type ReaderTheme = "paper" | "warm" | "night";
export type ReaderFont = "serif" | "sans" | "system";

export const FONT_STACKS: Record<ReaderFont, string> = {
  serif: '"Songti SC", SimSun, "Noto Serif CJK SC", serif',
  sans: '"PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif',
  system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
};

export const FONT_OPTIONS: { value: ReaderFont; label: string; stack: string }[] = [
  { value: "serif", label: "宋体", stack: FONT_STACKS.serif },
  { value: "sans", label: "黑体", stack: FONT_STACKS.sans },
  { value: "system", label: "系统", stack: FONT_STACKS.system },
];

export type ReaderSyncState =
  | "idle"
  | "syncing"
  | "synced"
  | "failed"
  | "remote_newer";
