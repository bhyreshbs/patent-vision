"use client";

import { useEffect, useState } from "react";
import { fetchBlob } from "@/lib/api";

interface Props {
  /** API path such as /ai/results/3/download?kind=mask. Null renders the placeholder. */
  src: string | null;
  alt: string;
  className?: string;
  placeholder?: string;
  /** Change this to force a reload (e.g. after reprocessing). */
  version?: string | number;
}

/** <img> for protected API files: fetches with the bearer token and shows a blob URL. */
export function SecureImage({ src, alt, className = "", placeholder = "Not available", version }: Props) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    if (!src) return;
    fetchBlob(src)
      .then((blob) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => !revoked && setFailed(true));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src, version]);

  if (!src || failed) {
    return (
      <div className={`flex items-center justify-center text-sm text-slate-400 ${className}`}>
        {failed ? "Could not load" : placeholder}
      </div>
    );
  }
  if (!url) return <div className={`animate-pulse bg-slate-100 ${className}`} aria-label="Loading" />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className={className} />;
}
