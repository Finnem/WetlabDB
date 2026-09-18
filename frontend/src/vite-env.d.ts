/// <reference types="vite/client" />

declare module "3dmol" {
  export interface GLViewer {
    addModel(data: string, format: string): void;
    setStyle(
      sel: Record<string, unknown>,
      style: Record<string, unknown>
    ): void;
    zoomTo(): void;
    resize(w: number, h: number): void;
    render(): void;
  }
  function createViewer(
    element: HTMLElement,
    options?: { backgroundColor?: string }
  ): GLViewer;
  const $3Dmol: { createViewer: typeof createViewer };
  export default $3Dmol;
}
