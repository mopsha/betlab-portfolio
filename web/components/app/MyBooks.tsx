"use client";

import { createContext, useContext } from "react";
import { onBooks, type Book } from "@/lib/books";

/** The books the signed-in account has on (user_settings.books_off, Nov 6, 0043), given to client components (tickets,
 *  Build, promos, ladder, book menus) by the root layout. Server pages get offers already at these books (data.ts). */
const Ctx = createContext<Book[]>(onBooks([]));
export const MyBooksProvider = ({ off, children }: { off: string[]; children: React.ReactNode }) =>
  <Ctx.Provider value={onBooks(off)}>{children}</Ctx.Provider>;
export const useMyBooks = () => useContext(Ctx);
