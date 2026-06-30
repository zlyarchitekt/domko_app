import { BspResult } from "./types";

/** Przykładowy wynik BSP na podstawie prostokątnej klatki 14m x 12m. */
export const sampleBspResult: BspResult = {
  footprint: [
    { x: 0, y: 0 },
    { x: 14, y: 0 },
    { x: 14, y: 12 },
    { x: 0, y: 12 },
  ],
  areas: [
    {
      id: "stairwell-1",
      type: "stairwell",
      name: "Klatka schodowa",
      points: [
        { x: 0, y: 0 },
        { x: 4, y: 0 },
        { x: 4, y: 4 },
        { x: 0, y: 4 },
      ],
    },
    {
      id: "corridor-1",
      type: "corridor",
      name: "Korytarz",
      points: [
        { x: 4, y: 1.5 },
        { x: 14, y: 1.5 },
        { x: 14, y: 3 },
        { x: 4, y: 3 },
      ],
    },
    {
      id: "apt-1",
      type: "apartment",
      name: "Mieszkanie 1 (2-pok)",
      apartmentType: "2",
      points: [
        { x: 4, y: 3 },
        { x: 9, y: 3 },
        { x: 9, y: 7.5 },
        { x: 4, y: 7.5 },
      ],
    },
    {
      id: "apt-2",
      type: "apartment",
      name: "Mieszkanie 2 (3-pok)",
      apartmentType: "3",
      points: [
        { x: 9, y: 3 },
        { x: 14, y: 3 },
        { x: 14, y: 7.5 },
        { x: 9, y: 7.5 },
      ],
    },
    {
      id: "apt-3",
      type: "apartment",
      name: "Mieszkanie 3 (1-pok)",
      apartmentType: "1",
      points: [
        { x: 4, y: 7.5 },
        { x: 8, y: 7.5 },
        { x: 8, y: 12 },
        { x: 4, y: 12 },
      ],
    },
    {
      id: "apt-4",
      type: "apartment",
      name: "Mieszkanie 4 (2-pok)",
      apartmentType: "2",
      points: [
        { x: 8, y: 7.5 },
        { x: 14, y: 7.5 },
        { x: 14, y: 12 },
        { x: 8, y: 12 },
      ],
    },
  ],
};
