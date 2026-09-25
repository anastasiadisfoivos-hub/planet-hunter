import type { ButtonHTMLAttributes, ReactNode } from "react";
import s from "./ui.module.css";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** primary: ink fill, one per view. ghost: bordered. quiet: text only, for toolbars. */
  variant?: "primary" | "ghost" | "quiet";
  size?: "md" | "sm";
  /** Leading icon. For an icon-only button, pass `icon` with no children and an `aria-label`. */
  icon?: ReactNode;
  block?: boolean;
};

export function Button({ variant = "ghost", size = "md", icon, block, className, children, type = "button", ...rest }: ButtonProps) {
  const cls = [
    s.button,
    s[variant],
    size === "sm" && s.sm,
    icon && !children && s.iconOnly,
    block && s.block,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={cls} {...rest}>
      {icon}
      {children}
    </button>
  );
}
