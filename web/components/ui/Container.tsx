/** The 1880 full-bleed band inset by the 20px gutter. */
export function Band({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: React.ElementType;
}) {
  return (
    <Tag className={`mx-auto w-full max-w-[1880px] px-[var(--gutter)] ${className}`}>
      {children}
    </Tag>
  );
}

/** The 1168 reading column, centred with generous side margins on desktop. */
export function Container({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: React.ElementType;
}) {
  return (
    <Tag
      className={`mx-auto w-full max-w-[1168px] px-6 md:px-10 xl:px-0 ${className}`}
    >
      {children}
    </Tag>
  );
}
