/*
 * Jarvis.app — macOS launcher
 *
 * This binary lives at Contents/MacOS/jarvis.  macOS registers it as
 * com.gambastudio.jarvis and that identity never changes because we load
 * Python via dlopen (no exec — the process image stays as *this* binary).
 *
 * Compile (done by build_app.sh):
 *   clang -Wall -O2 -o jarvis launcher.c
 */

#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* ── Python C-API symbols we need ─────────────────────────────────────── */
typedef int     (*t_Py_Main)          (int argc, wchar_t **argv);
typedef wchar_t*(*t_Py_DecodeLocale)  (const char *arg, size_t *size);
typedef void    (*t_PyMem_RawFree)    (void *p);

int main(int argc, char *argv[])
{
    /* 1. Resolve our own path (Contents/MacOS/jarvis). */
    char exe[4096];
    uint32_t exe_size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &exe_size) != 0) {
        fprintf(stderr, "jarvis: _NSGetExecutablePath failed\n");
        return 1;
    }

    /* 2. CFProcessPath — tells NSBundle/CF that our bundle is Jarvis.app. */
    setenv("CFProcessPath", exe, 1);

    /* 3. Build venv site-packages path: Contents/MacOS/../Resources/venv/... */
    char macos_dir[4096];
    strncpy(macos_dir, exe, sizeof(macos_dir) - 1);
    char *slash = strrchr(macos_dir, '/');
    if (slash) *slash = '\0';   /* macos_dir = .../Contents/MacOS */

    char site_packages[4096];
    snprintf(site_packages, sizeof(site_packages),
             "%s/../Resources/venv/lib/python3.12/site-packages", macos_dir);

    const char *existing = getenv("PYTHONPATH");
    if (existing && *existing) {
        char merged[8192];
        snprintf(merged, sizeof(merged), "%s:%s", site_packages, existing);
        setenv("PYTHONPATH", merged, 1);
    } else {
        setenv("PYTHONPATH", site_packages, 1);
    }

    /* 4. Load the Python 3.12 framework dylib. */
    const char *fw_dylib =
        "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework"
        "/Versions/3.12/Python";

    void *handle = dlopen(fw_dylib, RTLD_LAZY | RTLD_GLOBAL);
    if (!handle) {
        fprintf(stderr, "jarvis: cannot load Python framework: %s\n", dlerror());
        fprintf(stderr, "        Looked at: %s\n", fw_dylib);
        return 1;
    }

    t_Py_Main         Py_Main        = dlsym(handle, "Py_Main");
    t_Py_DecodeLocale Py_DecodeLocale= dlsym(handle, "Py_DecodeLocale");
    t_PyMem_RawFree   PyMem_RawFree  = dlsym(handle, "PyMem_RawFree");

    if (!Py_Main || !Py_DecodeLocale) {
        fprintf(stderr, "jarvis: required Python symbols not found\n");
        return 1;
    }

    /* 5. Build wchar_t argv for Py_Main.
     *
     * When macOS launches the app normally: argc == 1, no extra args.
     *   → run: jarvis -S -m jarvis.ui.macos_app
     *
     * When Python's multiprocessing spawns a worker it calls us with extra
     * args, e.g.:  jarvis -S -c "from multiprocessing.spawn import ..."
     *   → pass those args through unchanged so the worker runs correctly
     *     and does NOT start the full GUI app again.
     */
    const char **py_args;
    int          py_argc;

    const char *default_args[] = { exe, "-S", "-m", "jarvis.ui.macos_app" };

    if (argc > 1) {
        /* Forward original argv (replace argv[0] with resolved exe path). */
        py_argc = argc;
        py_args = (const char **)argv;
        py_args[0] = exe;   /* use realpath so Python can find itself */
    } else {
        py_args = default_args;
        py_argc = 4;
    }

    wchar_t **py_argv = calloc(py_argc + 1, sizeof(wchar_t *));
    if (!py_argv) { perror("jarvis: calloc"); return 1; }

    for (int i = 0; i < py_argc; i++) {
        py_argv[i] = Py_DecodeLocale(py_args[i], NULL);
        if (!py_argv[i]) {
            fprintf(stderr, "jarvis: Py_DecodeLocale failed for arg %d\n", i);
            return 1;
        }
    }

    /* 6. Hand off to Python — this starts the runloop and never returns
          until the app quits. */
    int rc = Py_Main(py_argc, py_argv);

    /* Cleanup (reached only on exit). */
    if (PyMem_RawFree)
        for (int i = 0; i < py_argc; i++)
            PyMem_RawFree(py_argv[i]);
    free(py_argv);

    return rc;
}
