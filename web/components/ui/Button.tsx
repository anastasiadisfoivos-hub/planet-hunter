import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import s from "./ui.module.css";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** primary: ink fill, one per view. ghost: bordered. quiet: text only, for toolbars. */
  variant?: "primary" | "ghost" | "quiet";
  size?: "md" | "sm";
  /** Leading icon. For an icon-only button, pass `icon` with no children and an `aria-label`. */
  icon?: ReactNode;
  block?: boolean;
};

function classes(variant: string, size: string, icon: ReactNode, hasChildren: boolean, block: boolean | undefined, className: string | undefined) {
  return [s.button, s[variant], size === "sm" && s.sm, icon && !hasChildren && s.iconOnly, block && s.block, className].filter(Boolean).join(" ");
}

/** A link that looks like a button: for navigation (Open in sky, Try again elsewhere). */
export function ButtonLink({
  href,
  variant = "ghost",
  size = "md",
  icon,
  block,
  className,
  children,
  ...rest
}: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; variant?: "primary" | "ghost" | "quiet"; size?: "md" | "sm"; icon?: ReactNode; block?: boolean }) {
  return (
    <Link href={href} className={classes(variant, size, icon, !!children, block, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

export function Button({ variant = "ghost", size = "md", icon, block, className, children, type = "button", ...rest }: ButtonProps) {
  const cls = classes(variant, size, icon, !!children, block, className);
  return (
    <button type={type} className={cls} {...rest}>
      {icon}
      {children}
    </button>
  );
}
