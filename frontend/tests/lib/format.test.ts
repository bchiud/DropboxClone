import { describe, expect, it } from "vitest";
import { middleTruncate } from "../../src/lib/format";

const ELLIPSIS = "…";

describe("middleTruncate", () => {
  it("leaves a name shorter than max untouched", () => {
    expect(middleTruncate("blank.pdf")).toBe("blank.pdf");
  });

  it("leaves a name exactly max chars untouched", () => {
    const name = "a".repeat(44);
    expect(middleTruncate(name)).toBe(name);
  });

  it("truncates at one char over max", () => {
    const name = "a".repeat(45);
    const out = middleTruncate(name);
    expect(out).not.toBe(name);
    expect(out).toContain(ELLIPSIS);
  });

  it("never exceeds max, however long the input", () => {
    for (const len of [45, 60, 200, 5000]) {
      expect(middleTruncate("a".repeat(len))).toHaveLength(44);
    }
  });

  it("keeps the extension — the point of truncating the middle", () => {
    const name = `${"quarterly-report-".repeat(5)}FINAL-v3.tar.gz`;
    const out = middleTruncate(name);
    expect(out.endsWith(".tar.gz")).toBe(true);
  });

  it("keeps the head, so names stay distinguishable", () => {
    const a = middleTruncate(`alpha-${"x".repeat(60)}.pdf`);
    const b = middleTruncate(`bravo-${"x".repeat(60)}.pdf`);
    expect(a.startsWith("alpha-")).toBe(true);
    expect(b.startsWith("bravo-")).toBe(true);
    expect(a).not.toBe(b);
  });

  it("cuts the middle, not the end", () => {
    const name = `${"a".repeat(40)}${"b".repeat(40)}.pdf`;
    const out = middleTruncate(name);
    const [head, tail] = out.split(ELLIPSIS);
    expect(head).toMatch(/^a+$/); // head is all from the start
    expect(tail.endsWith(".pdf")).toBe(true); // tail is all from the end
  });

  it("honours a custom max", () => {
    expect(middleTruncate("a".repeat(50), 20)).toHaveLength(20);
    expect(middleTruncate("a".repeat(50), 10)).toHaveLength(10);
  });

  it("caps the tail at 12 chars so the head keeps growing with max", () => {
    const name = `${"a".repeat(80)}.pdf`;
    const out = middleTruncate(name, 60);
    const [, tail] = out.split(ELLIPSIS);
    expect(tail).toHaveLength(12);
  });
});
