import Link from "next/link";

export function ErrorNote({ message }: { message: string }) {
  const signIn = message.startsWith("Sign in");
  return (
    <p className="text-xs text-destructive">
      {message}
      {signIn && (
        <>
          {" "}
          <Link href="/signin" className="underline">
            Sign in
          </Link>
        </>
      )}
    </p>
  );
}
