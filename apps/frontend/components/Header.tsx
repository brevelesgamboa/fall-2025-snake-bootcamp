"use client";

import { ThemeButton } from "@/components/theme-button";
import { Button } from "./ui/button";

import Link from "next/link";
import { useState } from "react";

// basic header
export const Header = () => {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <header className="flex items-center justify-between h-full px-4 md:px-6 p-4 bg-card border-b border-primary border-b-[1px] relative">
      <Link href="/" className="px-4 no-underline">
        <span className="text-xl font-bold text-primary">
          AI Snake
        </span>
      </Link>
      {/* Desktop Nav */}
      <div className="hidden sm:flex items-center space-x-2">
        <Button asChild variant="link">
          <Link href="/">home</Link>
        </Button>
        <Button asChild variant="link">
          <Link href="/about">about</Link>
        </Button>
        <Button asChild>
          <a href="/Resume.pdf" download="Resume.pdf">
            resume
          </a>
        </Button>
        <ThemeButton />
      </div>
      {/* Mobile Hamburger */}
      <div className="sm:hidden flex">
        <button
          className="p-2 focus:outline-none"
          aria-label="Open menu"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <svg
            width="28"
            height="28"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-primary"
          >
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </button>
        {menuOpen && (
          <div className="absolute top-full right-4 mt-2 bg-card rounded-lg shadow-lg flex flex-col items-start p-4 z-50 min-w-[150px]">
            <Button
              asChild
              variant="link"
              className="w-full mb-2"
              onClick={() => setMenuOpen(false)}
            >
              <Link href="/">home</Link>
            </Button>
            <Button
              asChild
              variant="link"
              className="w-full mb-2"
              onClick={() => setMenuOpen(false)}
            >
              <Link href="/about">about</Link>
            </Button>
            <Button
              asChild
              className="w-full mb-2"
              onClick={() => setMenuOpen(false)}
            >
              <a href="/Resume.pdf" download="Resume.pdf">
                resume
              </a>
            </Button>
            <ThemeButton />
          </div>
        )}
      </div>
    </header>
  );
};
