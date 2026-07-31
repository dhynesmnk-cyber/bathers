// Zero-dependency resolve hook: lets native Node load the project's extensionless
// relative TS imports (e.g. comparisons.ts's `from "../config"`) without touching
// site source. Used only by build-support scripts in this directory.
export async function resolve(specifier, context, nextResolve) {
  try {
    return await nextResolve(specifier, context);
  } catch (err) {
    if ((specifier.startsWith("./") || specifier.startsWith("../")) && !/\.[cm]?[jt]sx?$/i.test(specifier)) {
      return await nextResolve(specifier + ".ts", context);
    }
    throw err;
  }
}
