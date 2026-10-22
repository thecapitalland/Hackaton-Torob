import { faFloor } from "../format";

/**
 * «پاساژ علاالدین · طبقه ۲» — B4: empty parts never leave a trailing « · ».
 */
export function shopLocationLine(
  mall: string | null | undefined,
  floor: string | null | undefined,
): string {
  return [mall ?? "", floor ? `طبقه ${faFloor(floor)}` : ""]
    .filter(Boolean)
    .join(" · ");
}
