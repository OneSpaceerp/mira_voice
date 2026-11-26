import type * as React from 'react';
/** Primary = the one action a view is for (red). Secondary for everything else. Danger = destructive, terracotta. */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md' | 'lg'; icon?: IconName; }
export declare function Button(props: ButtonProps): React.ReactElement;
export type AgentStatus = 'available' | 'ringing' | 'on-call' | 'hold' | 'wrap-up' | 'break' | 'offline';
/** Agent or call state. Always dot + word; colour is never the only cue. lang picks the built-in label. */
export interface StatusPillProps { status: AgentStatus; label?: string; timer?: string; lang?: 'en' | 'ar' | 'fr'; className?: string; }
export declare function StatusPill(props: StatusPillProps): React.ReactElement;
export interface CallField { label: string; value: React.ReactNode; }
/** The docked call panel in Mira Desk and the call screen of Mira Phone. fields = the ERPNext customer card. */
export interface CallPanelProps { state?: 'ringing' | 'connected' | 'hold'; callerName?: string; number?: string; queue?: string; timer?: string; fields?: CallField[]; onAnswer?: () => void; onDecline?: () => void; onHangup?: () => void; onTransfer?: () => void; onKeypad?: () => void; className?: string; }
export declare function CallPanel(props: CallPanelProps): React.ReactElement;
/** 3x4 dial pad with display, delete and call button. Always LTR, even in Arabic. */
export interface DialPadProps { defaultValue?: string; placeholder?: string; onChange?: (value: string) => void; onCall?: (value: string) => void; className?: string; }
export declare function DialPad(props: DialPadProps): React.ReactElement;
/** One KPI. status sets the word and tint; size 'wallboard' is the TV version (always dark). */
export interface KpiTileProps { label: string; value: React.ReactNode; unit?: string; target?: string; trend?: string; status?: 'ok' | 'warn' | 'bad'; size?: 'md' | 'wallboard'; className?: string; }
export declare function KpiTile(props: KpiTileProps): React.ReactElement;
/** Labelled input with hint or error. mono for phone numbers and extensions. */
export interface TextFieldProps extends React.InputHTMLAttributes<HTMLInputElement> { label: string; hint?: string; error?: string; mono?: boolean; }
export declare function TextField(props: TextFieldProps): React.ReactElement;
export type IconName = 'phone' | 'mic' | 'micOff' | 'pause' | 'transfer' | 'keypad' | 'record' | 'back' | 'trendUp' | 'trendDown' | 'alert';
export interface IconProps { name: IconName; size?: number; weight?: number; className?: string; style?: React.CSSProperties; }
export declare function Icon(props: IconProps): React.ReactElement;
declare global { interface Window { MiraVoice: { Button: typeof Button; StatusPill: typeof StatusPill; CallPanel: typeof CallPanel; DialPad: typeof DialPad; KpiTile: typeof KpiTile; TextField: typeof TextField; Icon: typeof Icon } } }
