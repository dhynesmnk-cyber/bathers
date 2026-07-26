// Margin-decoration animal artwork (DESIGN.md §6a). Unlike paths.ts these
// are raster sources (user-supplied, TRD.md §3's `Icons and logos/`),
// downscaled/alpha-cropped into site/public/animals/ — MarginAnimal.astro
// recolours them via CSS mask rather than inline SVG/currentColor stroke.

export type AnimalKey =
  | "seal"
  | "capybara"
  | "penguin"
  | "otter"
  | "red-panda"
  | "otter-tub"
  | "polar-bear"
  | "kangaroo"
  | "frog";

export const ANIMAL_SRC: Record<AnimalKey, string> = {
  seal: "/animals/seal.png",
  capybara: "/animals/capybara.png",
  penguin: "/animals/penguin.png",
  otter: "/animals/otter.png",
  "red-panda": "/animals/red-panda.png",
  "otter-tub": "/animals/otter-tub.png",
  "polar-bear": "/animals/polar-bear.png",
  kangaroo: "/animals/kangaroo.png",
  frog: "/animals/frog.png",
};
