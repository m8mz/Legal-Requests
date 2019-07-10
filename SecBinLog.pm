package SecBinLog;

use strict;
use warnings;

use constant {
    LOGPATH => '/var/log/legacy',
    LOGFILE => 'sec-bin.log',
};

sub sb_log {
    my $args = shift || {};

    my $logpath = $args->{'path'} || LOGPATH;
    my $log_fn  = $args->{'file'} || LOGFILE;

    local $INC{'FindBin.pm'};
    delete $INC{'FindBin.pm'};
    require FindBin;
    require File::Spec::Functions;
    no warnings qw(once);

    my $log_fullname = File::Spec::Functions::catfile($logpath, $log_fn);
    my $scriptname   = File::Spec::Functions::catfile($FindBin::RealBin, $FindBin::RealScript) || '';
    my $warning      = "$scriptname: Unable to open $log_fullname for append. No log entry will be generated.";

    if(!-e $logpath || !-d $logpath) {
        warn "$warning\n"
    }
    else {
        if (open my $log, '>>', $log_fullname) {
            require Cwd;
            printf {$log} "[%s] <%s> (%s) - command: %s - cwd: %s - perl: %s - args: (%s)\n",
                scalar(localtime(time)),                        # [%s] - timestamp
                (defined $$ ? $$ : ''),                         # <%s> - pid
                (defined $ENV{'USER'} ? $ENV{'USER'} : ''),     # (%s) - Username
                $scriptname,                                    # command: %s
                (Cwd::cwd() || ''),                             # cwd: %s - working directory.
                (defined $^X ? $^X : ''),                       # perl: %s - Path to Perl interpreter.
                (join(' ', grep{m/^--?\w+$/} @ARGV) || '');     # args: (%s):  Hyphenated args.

                close $log or warn "Failed to close log ($log_fullname) after append.\n";
                chmod 0622, $log_fullname; # Quietly tolerate failure. Next run will fix it.
        }
        else {
            warn "$warning: $!\n";
        }
    }
}

1;

__END__

=head1 NAME

    SecBinLog - Perl module to log calls to C</sec/bin/*> scripts.

=head1 SYNOPSIS

    use FindBin;
    use lib $FindBin::Bin . '/../lib';

    use SecBinLog;
    sb_log({}); # Writes an entry to /var/log/legacy/sec-bin.log

=head1 DESCRIPTION

    This Perl module deduces its caller and creates an "I was here" entry into the logfile at
    C</var/log/legacy/sec-bin.log>.

    The actual entry looks like:

    C<[Mon May  8 14:19:41 2017] <24621> (doswald) - command: /var/userbox/t/sec_bin_log.t - cwd: /var/userbox - perl: /usr/bin/perl - args: ()>

=head1 PARAMETERS

=over 4

=item path

An alternate path where the logfile should exist.  Default is C</var/log/legacy>.

=item file

An alternate filename for the logfile. Default is C<sec-bin.log>.

=back

=head1 RATIONALE

We need to identify when C</sec/bin/*> scripts are being called, how they're being called, and whom is
calling them. By providing a common logging tool that can be dropped into the C</sec/bin> scripts we can
gain better transparency, B<and> verify our assumptions when we believe we've removed all calls to the
target scripts.

=head1 SETUP

The log file must exist with appropriately permissive permissions so that the logging can happen
regardless of who called the script.

If the log file does not exist, an attempt will be made to create one and set its permissions. But this will
only work if the caller is running as root, which would probably never really happen.

It is recommended that the following call be made on all active servers to enable the logging:

    BEGIN {
        require '/usr/sec/lib/SecBinLog.pm';
        SecBinLog::sb_log(); # Writes an entry to /var/log/legacy/sec-bin.log
    }

For shell scripts use the following (which does not use this module, but is effective):


    echo "[`date`] <$$> (${USER}) - command: $0 - cwd: ${PWD} - shell: $SHELL" >> /var/log/legacy/sec-bin.log

=cut
