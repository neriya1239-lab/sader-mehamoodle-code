// "סדר מהמודל" – the Mac launcher (for the kit's maintainer: built, signed and notarized by "בניית גרסת Mac.command").
// One small program inside each launcher app ("התקנת סידור אוטומטי.app", "הגדרות.app", ...). Each app's Info.plist
// holds its flag (SaderFlag = --install / --setup / ...). It replaces the old .command files, which Gatekeeper blocked
// ("Apple could not verify") because a script cannot be signed or notarized; an app can.
//
// What it does, step by step:
//   1. Finds where the app really is. An app that came from the Internet (a ZIP, AirDrop, a shared iCloud folder) and
//      was not moved is started by macOS from a random read-only copy ("App Translocation"), where the folder
//      "מערכת" next to it cannot be seen. Security.framework tells us the original place.
//   2. Finds the kit folder "מערכת": next to the app (the ZIP: the apps at the top) or one level up (the kit: in Mac/).
//   3. Writes a short script to this user's private temporary folder and opens it in Terminal. It does exactly what the
//      old .command did: runs מערכת/bin-mac/MoodleSorter.app with the flag (or python3 sort_downloads.py), in a window
//      where the questions can be answered. A file this program writes itself is not marked "from the Internet",
//      so Terminal opens it with no Gatekeeper question. The script deletes itself when it starts.
// Nothing here needs a password, the network or any permission. Build: clang -arch arm64 -arch x86_64 ... -framework CoreFoundation
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <errno.h>
#include <libgen.h>
#include <limits.h>
#include <spawn.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

#define KIT_NAME "מערכת"

static void alert(const char *text) {          // a plain macOS message box (no Terminal needed)
    CFStringRef title = CFStringCreateWithCString(NULL, "סדר מהמודל", kCFStringEncodingUTF8);
    CFStringRef msg = CFStringCreateWithCString(NULL, text, kCFStringEncodingUTF8);
    CFUserNotificationDisplayAlert(0, kCFUserNotificationStopAlertLevel, NULL, NULL, NULL, title, msg, NULL, NULL, NULL, NULL);
    if (title) CFRelease(title);
    if (msg) CFRelease(msg);
}

static bool url_path(CFURLRef url, char *out, size_t size) {
    return url && CFURLGetFileSystemRepresentation(url, true, (UInt8 *)out, (CFIndex)size);
}

// The app's real location, also when macOS runs it from a translocated copy.
static bool original_bundle_path(char *out, size_t size) {
    CFURLRef bundle = CFBundleCopyBundleURL(CFBundleGetMainBundle());
    if (!bundle) return false;
    bool done = false;
    void *sec = dlopen("/System/Library/Frameworks/Security.framework/Security", RTLD_LAZY);
    if (sec) {
        Boolean (*is_translocated)(CFURLRef, bool *, CFErrorRef *) = dlsym(sec, "SecTranslocateIsTranslocatedURL");
        CFURLRef (*original)(CFURLRef, CFErrorRef *) = dlsym(sec, "SecTranslocateCreateOriginalPathForURL");
        bool translocated = false;
        if (is_translocated && original && is_translocated(bundle, &translocated, NULL) && translocated) {
            CFURLRef orig = original(bundle, NULL);
            if (orig) {
                done = url_path(orig, out, size);
                CFRelease(orig);
            }
        }
    }
    if (!done) done = url_path(bundle, out, size);
    CFRelease(bundle);
    return done;
}

static bool is_kit(const char *dir) {          // a "מערכת" folder of this tool
    char p[PATH_MAX];
    struct stat st;
    snprintf(p, sizeof p, "%s/sort_downloads.py", dir);
    if (stat(p, &st) == 0) return true;
    snprintf(p, sizeof p, "%s/bin-mac", dir);
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
}

static void put_quoted(FILE *f, const char *s) {   // a shell word in single quotes ('it'\''s')
    fputc('\'', f);
    for (; *s; s++) {
        if (*s == '\'') fputs("'\\''", f);
        else fputc(*s, f);
    }
    fputc('\'', f);
}

int main(int argc, char **argv) {
    char app[PATH_MAX], parent[PATH_MAX], kit[PATH_MAX], name[PATH_MAX];
    if (!original_bundle_path(app, sizeof app)) { alert("לא הצלחתי למצוא איפה הקובץ הזה נמצא."); return 1; }
    strlcpy(parent, app, sizeof parent);
    strlcpy(parent, dirname(parent), sizeof parent);
    strlcpy(name, app, sizeof name);
    strlcpy(name, basename(name), sizeof name);
    size_t n = strlen(name);
    if (n > 4 && strcmp(name + n - 4, ".app") == 0) name[n - 4] = 0;

    snprintf(kit, sizeof kit, "%s/" KIT_NAME, parent);                  // the ZIP: the apps at the top, next to מערכת
    if (!is_kit(kit)) snprintf(kit, sizeof kit, "%s/../" KIT_NAME, parent);   // the kit folder: the apps are in Mac/
    bool found = is_kit(kit);
    if (found) {
        char real[PATH_MAX];
        if (realpath(kit, real)) strlcpy(kit, real, sizeof kit);
    }

    CFStringRef flag_ref = CFBundleGetValueForInfoDictionaryKey(CFBundleGetMainBundle(), CFSTR("SaderFlag"));
    char flag[64] = "";
    if (!flag_ref || CFGetTypeID(flag_ref) != CFStringGetTypeID() ||
        !CFStringGetCString(flag_ref, flag, sizeof flag, kCFStringEncodingUTF8) || strncmp(flag, "--", 2) != 0) {
        alert("הקובץ הזה פגום (חסרה בו הפעולה). כדאי להוריד שוב את הכלי.");
        return 1;
    }
    for (const char *c = flag + 2; *c; c++)                               // only letters: it goes into the script
        if (!((*c >= 'a' && *c <= 'z') || *c == '-')) { alert("הקובץ הזה פגום. כדאי להוריד שוב את הכלי."); return 1; }

    // --version / --where: a quick check for the build and the tests (prints where it is, opens nothing)
    if (argc > 1 && (strcmp(argv[1], "--version") == 0 || strcmp(argv[1], "--where") == 0)) {
        CFStringRef v = CFBundleGetValueForInfoDictionaryKey(CFBundleGetMainBundle(), CFSTR("CFBundleShortVersionString"));
        char ver[32] = "?";
        if (v && CFGetTypeID(v) == CFStringGetTypeID()) CFStringGetCString(v, ver, sizeof ver, kCFStringEncodingUTF8);
        printf("SaderLauncher %s %s\napp: %s\nkit: %s\n", ver, flag, app, found ? kit : "(not found)");
        return found ? 0 : 2;
    }
    if (!found) {
        alert("לא מצאתי את התיקייה \"מערכת\" ליד הקובץ הזה.\n\n"
              "צריך להשאיר את כל התיקייה \"סדר מהמודל\" ביחד, כמו שיצאה מה-ZIP, ולהפעיל מתוכה.");
        return 1;
    }

    // the script, in this user's private temporary folder
    char tmpl[PATH_MAX];
    const char *tmp = getenv("TMPDIR");
    char tmpbuf[PATH_MAX];
    if (!tmp || !*tmp) {
        if (confstr(_CS_DARWIN_USER_TEMP_DIR, tmpbuf, sizeof tmpbuf) > 0) tmp = tmpbuf;
        else tmp = "/tmp/";
    }
    snprintf(tmpl, sizeof tmpl, "%s/sader.XXXXXX", tmp);
    if (!mkdtemp(tmpl)) { alert("לא הצלחתי לפתוח את החלון (אין מקום בדיסק?)."); return 1; }
    char script[PATH_MAX];
    snprintf(script, sizeof script, "%s/%s.command", tmpl, name);
    FILE *f = fopen(script, "w");
    if (!f) { alert("לא הצלחתי לפתוח את החלון."); return 1; }
    fputs("#!/bin/bash\n", f);
    fprintf(f, "# \"סדר מהמודל\" - %s (נוצר לרגע על ידי %s.app, ונמחק מיד)\n", flag, name);
    fputs("rm -f \"$0\"; rmdir \"$(dirname \"$0\")\" 2>/dev/null\n", f);
    fputs("clear 2>/dev/null\ncd ", f);   // (hides the line Terminal prints with this temporary path)
    put_quoted(f, kit);
    fputs(" || exit 1\n", f);
    fputs("P=bin-mac/MoodleSorter.app/Contents/MacOS/MoodleSorter\n", f);
    fputs("if [ -x \"$P\" ] && \"$P\" --version >/dev/null 2>&1; then\n", f);
    fprintf(f, "  \"$P\" %s                                   # the program itself, no Python needed\n", flag);
    fputs("elif command -v python3 >/dev/null 2>&1 && python3 -c \"import sys\" >/dev/null 2>&1; then\n", f);
    fprintf(f, "  python3 sort_downloads.py %s\n", flag);
    fputs("else\n"
          "  echo \"\"\n"
          "  echo \"Python לא מותקן במק, והכלי צריך אותו.\"\n"
          "  echo \"1. אם קפץ חלון שמציע להתקין 'כלי שורת פקודה' (Command Line Tools) - ללחוץ 'התקן'.\"\n"
          "  echo \"   או להוריד Python מ-https://www.python.org/downloads/\"\n", f);
    fprintf(f, "  echo \"2. אחרי ההתקנה ללחוץ שוב לחיצה כפולה על %s.\"\n", name);
    fputs("fi\n"
          "echo \"\"\n"
          "read -t 120 -n 1 -s -r -p \"אפשר לסגור את החלון (או ללחוץ על מקש כלשהו).\"\n"
          "echo \"\"\n", f);
    if (fclose(f) != 0 || chmod(script, 0700) != 0) { alert("לא הצלחתי לפתוח את החלון."); return 1; }

    if (getenv("SADER_LAUNCHER_DRYRUN")) {               // tests only: write the script, print where, open nothing
        printf("%s\n", script);
        return 0;
    }
    // open it in Terminal (like double-clicking the old .command)
    char *args[] = {"/usr/bin/open", "-a", "Terminal", script, NULL};
    pid_t pid;
    int rc = posix_spawn(&pid, args[0], NULL, NULL, args, environ), status = 0;
    if (rc == 0) waitpid(pid, &status, 0);
    if (rc != 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        unlink(script); rmdir(tmpl);
        alert("לא הצלחתי לפתוח את Terminal.");
        return 1;
    }
    return 0;
}
