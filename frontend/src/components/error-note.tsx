import Link from "next/link";

/** The API puts a request id on every failure; show it separately so it can be quoted. */
const REF = /\s\(ref ([A-Za-z0-9._-]{1,64})\)/;

export function ErrorNote({ message }: { message: string }) {
  const signIn = message.startsWith("Sign in");
  const ref = message.match(REF);
  const text = ref ? message.replace(REF, "") : message;
  return (
    <p className="text-xs text-destructive">
      {text}
      {signIn && (
        <>
          {" "}
          <Link href="/signin" className="underline">
            Sign in
          </Link>
        </>
      )}
      {ref && <span className="ml-2 font-mono text-muted-foreground">ref {ref[1]}</span>}
    </p>
  );
}
