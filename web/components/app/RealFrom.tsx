"use client";

import { createContext, useContext } from "react";

/** The signed-in account's real-money start (user_settings.real_from; null = the default, Oct 18), given
 *  to client components like the Mark button by the root layout. */
const Ctx = createContext<string | null>(null);
export const RealFromProvider = ({ value, children }: { value: string | null; children: React.ReactNode }) =>
  <Ctx.Provider value={value}>{children}</Ctx.Provider>;
export const useRealFrom = () => useContext(Ctx);
