type Props = { message: string };

/** Live region for API / form errors (W7e a11y). */
export function ErrorAlert({ message }: Props) {
  if (!message) return null;
  return (
    <p className="text-sm text-flare" role="alert" aria-live="assertive">
      {message}
    </p>
  );
}
