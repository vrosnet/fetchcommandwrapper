#!/usr/bin/env python
# Copyright (C) 2010 Sebastian Pipping <sebastian@pipping.org>
# Copyright (C) 2010 Andrew Karpow <andy@mailbox.tu-berlin.de>
# Licensed under GPL v3 or later

MAX_STREAMS = 5
ARIA2_COMMAND = '/usr/bin/aria2c'


import sys
import os


def print_greeting():
    from fetchcommandwrapper.version import VERSION_STR
    print 'fetchcommandwrapper', VERSION_STR
    print


def parse_parameters():
    USAGE = "\n  %prog [OPTIONS] URI DISTDIR FILE"""

    from optparse import OptionParser
    from fetchcommandwrapper.version import VERSION_STR
    parser = OptionParser(usage=USAGE, version=VERSION_STR)

    parser.add_option("-c", "--continue",
        action="store_true", dest="continue_flag", default=False,
        help="continue previous download")
    parser.add_option("--fresh",
        action="store_false", dest="continue_flag", default=False,
        help="do not continue previous download (default)")
    parser.add_option("--link-speed",
        metavar="SPEED", dest="link_speed_bytes",
        help="specify link speed (bytes per second). enables dropping of slow connections.")

    (opts, args) = parser.parse_args()
    if len(args) != 3:
        parser.print_usage()
        sys.exit(1)

    # Check --link-speed
    if opts.link_speed_bytes:
        try:
            opts.link_speed_bytes = int(opts.link_speed_bytes)
        except ValueError:
            print >>sys.stderr, 'ERROR: Parameter --link-speed accepts numbers only.'
            sys.exit(1)

    opts.uri, opts.distdir, opts.file_basename = args
    opts.distdir = opts.distdir.rstrip('/')

    opts.file_fullpath = os.path.join(opts.distdir, opts.file_basename)

    return opts


def invoke_wget(opts):
    args = ['/usr/bin/wget', '-O', opts.file_fullpath]
    args.append('--tries=5')
    args.append('--timeout=60')
    args.append('--passive-ftp')
    if opts.continue_flag:
        args.append('--continue')
    args.append(opts.uri)

    # Invoke wget
    print 'Running... #', ' '.join(args)
    import subprocess
    return subprocess.call(args)


def print_invocation_details(opts):
    print 'URI = ' + opts.uri
    print 'DISTDIR = ' + opts.distdir
    print 'FILE = ' + opts.file_basename
    print


def gentoo_mirrors():
    import subprocess
    p = subprocess.Popen(['/usr/bin/portageq', 'gentoo_mirrors'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if err:
        print >>sys.stderr, 'ERROR', err
        sys.exit(1)
    return out.rstrip('\n').split(' ')


def supported(uri):
    return uri.startswith('http://') \
        or uri.startswith('https://') \
        or uri.startswith('ftp://')


def print_mirror_details(supported_mirror_uris):
    print 'Involved mirrors:'
    print '\n'.join('  - ' + e for e in supported_mirror_uris)
    print '  (%d mirrors)' % len(supported_mirror_uris)
    print

    if len(supported_mirror_uris) < MAX_STREAMS:
        print >>sys.stderr, 'WARNING:  Please specify at least %d URIs in GENTOO_MIRRORS.' % MAX_STREAMS
        print >>sys.stderr, '          The more the better.'
        print >>sys.stderr


def make_final_uris(uri, supported_mirror_uris):
    final_uris = [uri, ]
    mirrors_involved = False
    for i, mirror_uri in enumerate(supported_mirror_uris):
        if uri.startswith(mirror_uri):
            if i != 0:
                # Portage calls us for each mirror URI. Therefore we need to error out
                # on all but the first one, so we try each mirrror once, at most.
                # This happens, when a file is not mirrored, e.g. with sunrise ebuilds.
                print >>sys.stderr, 'ERROR: All Gentoo mirrors tried already, exiting.'
                sys.exit(1)

            mirrors_involved = True

            local_part = uri[len(mirror_uri):]
            final_uris = [e + local_part for e in supported_mirror_uris]
            import random
            random.shuffle(final_uris)
            break
    return final_uris, mirrors_involved


def invoke_aria2(opts, final_uris):
    # Compose call arguments
    wanted_connections = min(MAX_STREAMS, len(final_uris))
    if opts.link_speed_bytes and (len(final_uris) > MAX_STREAMS):
        drop_slow_links = True
    else:
        drop_slow_links = False

    if len(final_uris) > 1:
        print 'Targetting %d random connections, additional %d for backup' \
            % (wanted_connections, max(0, len(final_uris) - MAX_STREAMS))
        print

    args = [ARIA2_COMMAND, '-d', opts.distdir, '-o', opts.file_basename]
    if drop_slow_links:
        wanted_minimum_link_speed = opts.link_speed_bytes / wanted_connections / 3
        args.append('--lowest-speed-limit=%s' % wanted_minimum_link_speed)
    if opts.continue_flag:
        args.append('--continue')
    args.append('--max-tries=5')
    args.append('--user-agent=Wget/1.12')
    args.append('--split=%d' % wanted_connections)
    args.append('--max-connection-per-server=1')
    args.append('--uri-selector=inorder')
    args.extend(final_uris)

    # Invoke aria2
    print 'Running... #', ' '.join(args)
    import subprocess
    return subprocess.call(args)


def main():
    opts = parse_parameters()

    if not os.path.exists(ARIA2_COMMAND):
        print >>sys.stderr, 'ERROR: net-misc/aria2 not installed, falling back to net-misc/wget'
        ret = invoke_wget(opts)
        sys.exit(ret)

    if not os.path.isdir(opts.distdir):
        print >>sys.stderr, 'ERROR: Path "%s" not a directory' % opts.distdir
        sys.exit(1)

    if opts.continue_flag:
        if not os.path.isfile(opts.file_fullpath):
            print >>sys.stderr, 'ERROR: Path "%s" not an existing file' % opts.file_fullpath
            sys.exit(1)

    supported_mirror_uris = [e for e in gentoo_mirrors() if supported(e)]

    final_uris, mirrors_involved = make_final_uris(opts.uri, supported_mirror_uris)

    print_greeting()
    print_invocation_details(opts)

    if mirrors_involved:
        print_mirror_details(supported_mirror_uris)

    ret = invoke_aria2(opts, final_uris)
    sys.exit(ret)


if __name__ == '__main__':
    main()
