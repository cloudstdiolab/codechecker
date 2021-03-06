# -------------------------------------------------------------------------
#                     The CodeChecker Infrastructure
#   This file is distributed under the University of Illinois Open Source
#   License. See LICENSE.TXT for details.
# -------------------------------------------------------------------------
"""
Defines the CodeChecker action for parsing a set of analysis results into a
human-readable format.
"""
from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from collections import defaultdict
import argparse
import os
import sys

from plist_to_html import PlistToHtml

from libcodechecker import package_context
from libcodechecker import suppress_handler
from libcodechecker import logger
from libcodechecker import util
from libcodechecker.analyze import plist_parser
from libcodechecker.analyze.skiplist_handler import SkipListHandler
from libcodechecker.output_formatters import twodim_to_str
from libcodechecker.report import Report, get_report_path_hash
# TODO: This is a cross-subpackage reference...

LOG = logger.get_logger('system')


def get_argparser_ctor_args():
    """
    This method returns a dict containing the kwargs for constructing an
    argparse.ArgumentParser (either directly or as a subparser).
    """

    return {
        'prog': 'CodeChecker parse',
        'formatter_class': argparse.ArgumentDefaultsHelpFormatter,

        # Description is shown when the command's help is queried directly
        'description': "Parse and pretty-print the summary and results from "
                       "one or more 'codechecker-analyze' result files. Bugs "
                       "which are commented by using \"false_positive\", "
                       "\"suppress\" and \"intentional\" source code "
                       "comments will not be printed by the `parse` command.",

        # Help is shown when the "parent" CodeChecker command lists the
        # individual subcommands.
        'help': "Print analysis summary and results in a human-readable "
                "format."
    }


def add_arguments_to_parser(parser):
    """
    Add the subcommand's arguments to the given argparse.ArgumentParser.
    """

    parser.add_argument('input',
                        type=str,
                        nargs='+',
                        metavar='file/folder',
                        help="The analysis result files and/or folders "
                             "containing analysis results which should be "
                             "parsed and printed.")

    parser.add_argument('-t', '--type', '--input-format',
                        dest="input_format",
                        required=False,
                        choices=['plist'],
                        default='plist',
                        help="Specify the format the analysis results were "
                             "created as.")

    output_opts = parser.add_argument_group("export arguments")
    output_opts.add_argument('-e', '--export',
                             dest="export",
                             required=False,
                             choices=['html'],
                             help="Specify extra output format type.")

    output_opts.add_argument('-o', '--output',
                             dest="output_path",
                             help="Store the output in the given folder.")

    output_opts.add_argument('-c', '--clean',
                             dest="clean",
                             required=False,
                             action='store_true',
                             default=True,
                             help="DEPRECATED. Delete output results stored "
                                  "in the output directory. (By default, it "
                                  "would keep output files and overwrites "
                                  "only those that belongs to a plist file "
                                  "given by the input argument.")

    parser.add_argument('--suppress',
                        type=str,
                        dest="suppress",
                        default=argparse.SUPPRESS,
                        required=False,
                        help="Path of the suppress file to use. Records in "
                             "the suppress file are used to suppress the "
                             "display of certain results when parsing the "
                             "analyses' report. (Reports to an analysis "
                             "result can also be suppressed in the source "
                             "code -- please consult the manual on how to "
                             "do so.) NOTE: The suppress file relies on the "
                             "\"bug identifier\" generated by the analyzers "
                             "which is experimental, take care when relying "
                             "on it.")

    parser.add_argument('--export-source-suppress',
                        dest="create_suppress",
                        action="store_true",
                        required=False,
                        default=argparse.SUPPRESS,
                        help="Write suppress data from the suppression "
                             "annotations found in the source files that were "
                             "analyzed earlier that created the results. "
                             "The suppression information will be written "
                             "to the parameter of '--suppress'.")

    parser.add_argument('--print-steps',
                        dest="print_steps",
                        action="store_true",
                        required=False,
                        default=argparse.SUPPRESS,
                        help="Print the steps the analyzers took in finding "
                             "the reported defect.")

    parser.add_argument('-i', '--ignore', '--skip',
                        dest="skipfile",
                        required=False,
                        default=argparse.SUPPRESS,
                        help="Path to the Skipfile dictating which project "
                             "files should be omitted from analysis. Please "
                             "consult the User guide on how a Skipfile "
                             "should be laid out.")

    logger.add_verbose_arguments(parser)

    def __handle(args):
        """Custom handler for 'parser' so custom error messages can be
        printed without having to capture 'parser' in main."""

        def arg_match(options):
            return util.arg_match(options, sys.argv[1:])

        # --export cannot be specified without --output.
        export = ['-e', '--export']
        output = ['-o', '--output']
        if any(arg_match(export)) and not any(arg_match(output)):
            parser.error("argument --export: not allowed without "
                         "argument --output")

        # If everything is fine, do call the handler for the subcommand.
        main(args)

    parser.set_defaults(func=__handle)


def parse(plist_file, metadata_dict, rh, file_report_map):
    """
    Prints the results in the given file to the standard output in a human-
    readable format.

    Returns the report statistics collected by the result handler.
    """

    if not plist_file.endswith(".plist"):
        LOG.debug("Skipping input file '%s' as it is not a plist.", plist_file)
        return set()

    LOG.debug("Parsing input file '%s'", plist_file)

    if 'result_source_files' in metadata_dict and \
            plist_file in metadata_dict['result_source_files']:
        analyzed_source_file = \
            metadata_dict['result_source_files'][plist_file]

        if analyzed_source_file not in file_report_map:
            file_report_map[analyzed_source_file] = []

    files, reports = rh.parse(plist_file)

    plist_mtime = util.get_last_mod_time(plist_file)

    changed_files = set()
    for source_file in files:
        if plist_mtime is None:
            # Failed to get the modification time for
            # a file mark it as changed.
            changed_files.add(source_file)
            LOG.warning('%s is missing since the last analysis.', source_file)
            continue

        file_mtime = util.get_last_mod_time(source_file)
        if file_mtime > plist_mtime:
            changed_files.add(source_file)
            LOG.warning('%s did change since the last analysis.', source_file)

    if not changed_files:
        for report in reports:
            file_path = report.file_path
            if file_path not in file_report_map:
                file_report_map[file_path] = []

            file_report_map[file_path].append(report)

    return changed_files


def main(args):
    """
    Entry point for parsing some analysis results and printing them to the
    stdout in a human-readable format.
    """

    logger.setup_logger(args.verbose if 'verbose' in args else None)

    context = package_context.get_context()

    # To ensure the help message prints the default folder properly,
    # the 'default' for 'args.input' is a string, not a list.
    # But we need lists for the foreach here to work.
    if isinstance(args.input, str):
        args.input = [args.input]

    original_cwd = os.getcwd()

    suppr_handler = None
    if 'suppress' in args:
        __make_handler = False
        if not os.path.isfile(args.suppress):
            if 'create_suppress' in args:
                with open(args.suppress, 'w') as _:
                    # Just create the file.
                    __make_handler = True
                    LOG.info("Will write source-code suppressions to "
                             "suppress file.")
            else:
                LOG.warning("Suppress file '" + args.suppress + "' given, but "
                            "it does not exist -- will not suppress anything.")
        else:
            __make_handler = True

        if __make_handler:
            suppr_handler = suppress_handler.\
                GenericSuppressHandler(args.suppress,
                                       'create_suppress' in args)
    elif 'create_suppress' in args:
        LOG.error("Can't use '--export-source-suppress' unless '--suppress "
                  "SUPPRESS_FILE' is also given.")
        sys.exit(2)

    processed_path_hashes = set()

    def skip_html_report_data_handler(report_hash, source_file, report_line,
                                      checker_name, diag, files):
        """
        Report handler which skips bugs which were suppressed by source code
        comments.
        """
        report = Report(None, diag['path'], files)
        path_hash = get_report_path_hash(report, files)
        if path_hash in processed_path_hashes:
            LOG.debug("Skip report because it is a deduplication of an "
                      "already processed report!")
            LOG.debug("Path hash: %s", path_hash)
            LOG.debug(diag)
            return True

        skip = plist_parser.skip_report(report_hash,
                                        source_file,
                                        report_line,
                                        checker_name,
                                        suppr_handler)
        if not skip:
            processed_path_hashes.add(path_hash)

        return skip

    skip_handler = None
    if 'skipfile' in args:
        with open(args.skipfile, 'r') as skip_file:
            skip_handler = SkipListHandler(skip_file.read())

    html_builder = None

    for input_path in args.input:

        input_path = os.path.abspath(input_path)
        os.chdir(original_cwd)
        LOG.debug("Parsing input argument: '" + input_path + "'")

        export = args.export if 'export' in args else None
        if export is not None and export == 'html':
            output_path = os.path.abspath(args.output_path)

            if not html_builder:
                html_builder = \
                    PlistToHtml.HtmlBuilder(context.path_plist_to_html_dist,
                                            context.severity_map)

            LOG.info("Generating html output files:")
            PlistToHtml.parse(input_path,
                              output_path,
                              context.path_plist_to_html_dist,
                              skip_html_report_data_handler,
                              html_builder)
            continue

        files = []
        metadata_dict = {}
        if os.path.isfile(input_path):
            files.append(input_path)

        elif os.path.isdir(input_path):
            metadata_file = os.path.join(input_path, "metadata.json")
            if os.path.exists(metadata_file):
                metadata_dict = util.load_json_or_empty(metadata_file)
                LOG.debug(metadata_dict)

                if 'working_directory' in metadata_dict:
                    working_dir = metadata_dict['working_directory']
                    try:
                        os.chdir(working_dir)
                    except OSError as oerr:
                        LOG.debug(oerr)
                        LOG.error("Working directory %s is missing.\n"
                                  "Can not parse reports safely.", working_dir)
                        sys.exit(1)

            _, _, file_names = next(os.walk(input_path), ([], [], []))
            files = [os.path.join(input_path, file_name) for file_name
                     in file_names]

        file_change = set()
        file_report_map = defaultdict(list)

        rh = plist_parser.PlistToPlaintextFormatter(suppr_handler,
                                                    skip_handler,
                                                    context.severity_map,
                                                    processed_path_hashes)
        rh.print_steps = 'print_steps' in args

        for file_path in files:
            f_change = parse(file_path, metadata_dict, rh, file_report_map)
            file_change = file_change.union(f_change)

        report_stats = rh.write(file_report_map)
        severity_stats = report_stats.get('severity')
        file_stats = report_stats.get('files')
        reports_stats = report_stats.get('reports')

        print("\n----==== Summary ====----")
        if file_stats:
            vals = [[os.path.basename(k), v] for k, v in
                    dict(file_stats).items()]
            keys = ['Filename', 'Report count']
            table = twodim_to_str('table', keys, vals, 1, True)
            print(table)

        if severity_stats:
            vals = [[k, v] for k, v in dict(severity_stats).items()]
            keys = ['Severity', 'Report count']
            table = twodim_to_str('table', keys, vals, 1, True)
            print(table)

        report_count = reports_stats.get("report_count", 0)
        print("----=================----")
        print("Total number of reports: {}".format(report_count))
        print("----=================----")

        if file_change:
            changed_files = '\n'.join([' - ' + f for f in file_change])
            LOG.warning("The following source file contents changed since the "
                        "latest analysis:\n{0}\nMultiple reports were not "
                        "shown and skipped from the statistics. Please "
                        "analyze your project again to update the "
                        "reports!".format(changed_files))

    os.chdir(original_cwd)

    # Create index.html for the generated html files.
    if html_builder:
        html_builder.create_index_html(args.output_path)
