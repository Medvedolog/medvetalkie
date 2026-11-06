#include "medvetalkie/service.h"
#include <stdio.h>
#include <string.h>

int mt_scaffold_main(const char *service_name, int argc, char **argv)
{
    if (argc == 2 && (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0)) {
        printf("%s: MedveTalkie C11 process skeleton\n", service_name);
        printf("Usage: %s --help | --version\n", service_name);
        printf("Runtime not implemented yet: no hardware, audio or network support.\n");
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        printf("%s 0.0.1-dev\n", service_name);
        return 0;
    }
    fprintf(stderr, "%s: runtime NOT IMPLEMENTED (skeleton only).\n", service_name);
    return 78; /* EX_CONFIG; deliberately fail rather than pretend to run. */
}
