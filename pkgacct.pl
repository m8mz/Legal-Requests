#!/usr/bin/env perl
use strict;
use warnings;

use lib qw(/var/hp/common/lib);
use base qw(CommandLine);
use config;
use User;
use Debug;
use Data::Dumper;

__PACKAGE__->run;
exit;

sub exclusive { 'prompt' }

sub main {
	my $self = shift;
	my $args = $self->options;
	sub option_params {
               my $self = shift;
               return(
                   $self->SUPER::option_params(),
                   qw(
			domain|d=s
			log|l
			backup|b=s
			perms|p
			home|u
			dir=s
			all|a
			h
                   )
               );
	}
	my $help_message = <<HELP;
	Package Account for Legal
	    Help:
		sudo PROV=(bh|hm|jh) $0 -d <domain> -[a|l|b|p|h|d]

		-l|--log Grabs the logs for an account.
		-b|--backup <daily|weekly|monthly> Grabs a specific backup in case it failed etc.
		-p|--perms Fixes the permissions of the files (ownership gets updated to the user, and files/dirs updated)
		-u|--home Packages the home directory.
		--dir Sets the destination directory on the server. Defaults to "/home2/sd/" but in case it's full can be set differently.
		-a|--all Will grab the logs, backups, homedir, and update permissions.
		-h For this help page.
HELP
	sub option_defaults {
		return +{
			backup => ['daily', 'weekly', 'monthly'],
			dir => '/home2/sd/'
		};
	}
	
	my $help = $self->options->{'h'} || 0;
	if ($help) {
                print $help_message, "\n";
		exit;
        }

	my $domain = $self->options->{'domain'} || die "Must pass in a domain! Use '--help' for assistance.";
	my $log = $self->options->{'log'} || undef;
	my $backup = $self->options->{'backup'} || undef;
	my $perms = $self->options->{'perms'} || undef;
	my $home = $self->options->{'home'} || undef;
	my $all = $self->options->{'all'} || 0;

	my $user = User->new({ ldomain => $domain,$self->SHARE });
	my $return_value;
	# Default timeout of 300 sec. is causing problems, let's make it more patient ... 
	my $cpanel = $user->cpanel_obj;
	$cpanel->server->{'request_timeout'} = 86400;
	my $DIR = $self->options->{'dir'};
	my $USERNAME = $cpanel->username;
	my $CUSTBOX = $cpanel->server->hostname;
	my $DSTDIR = $DIR . $USERNAME;
	my $MAINDOMAIN = $user->main_domain;
	my (undef, undef, undef, $mday, $mon, $year) = localtime();
	$mon++;
	$year = $year+1900;
	$mday = 0 . $mday if $mday < 10;
	$mon = 0 . $mon if $mon < 10;
	my $DATE = "$year-$mon-$mday";
	my $domains = $user->domains;
	my $domains_list = '--domains=' . join(' --domains=', @$domains);
	my $CUSTHOME = $cpanel->server->whm_exec("getent passwd $USERNAME | awk -F: '{print \$6}'");
	chomp($CUSTHOME);
	my $BACKUP_NUM = $1 if ($CUSTHOME =~ /home(\d)/x);

	# Setting customer box variables
	$self->log ("On the legal server:\nexport MYUSER=" . $USERNAME . "\nexport CUSTBOX=" . $CUSTBOX . "\nexport DOMAIN=". $domain . "\nexport DSTDIR=" . $DSTDIR . "\nexport DATE=" . $DATE);
	$self->log("\nHostname:" . $cpanel->server->hostname . "\nUser:" . $USERNAME . "\nMain Domain:" . $MAINDOMAIN . "\nRequested Domain:" . $domain);

	# Creates legal directories for account
	my @dirs = ($DSTDIR, "$DSTDIR/non-home-data", "$DSTDIR/$USERNAME.seed", "$DSTDIR/$USERNAME.seed/homedir");
	foreach my $dir (@dirs) {
		print "Creating $dir\n";
		$cpanel->server->whm_exec("mkdir -p $dir");
	}

	# Grab logs for all domains
	if ($log || $all == 1) {
		print "Begin Log Grab.\n";
		my $exec = "nohup /usr/sec/bin/grablogs --tarfile=$DSTDIR/$USERNAME.logs.tar --cususer=$USERNAME $domains_list\n";
		$return_value    = eval { $cpanel->server->whm_exec($exec); };
		print "A Problem occurred running grablog: $@\n Taking too long?\n" if $@;
	}

	# Package account
	if ($home || $all == 1) {
		print "Starting Account Package.\n";
		$return_value = eval { $cpanel->server->whm_exec("/scripts/pkgacct --skiphomedir --skiplogs $USERNAME $DSTDIR/non-home-data 2>&1") };
		print "A Problem occurred running pkgacct: $@\n Taking too long?\n" if $@;

		 # Copy the homedir and backups
		print "Starting Copy Home Directory\n";
		$return_value    = $cpanel->server->whm_exec("nohup cp --preserve=links -xpr $CUSTHOME $DSTDIR/$USERNAME.home ");
		print "RSYNC Backups\n";
		$return_value    = $cpanel->server->whm_exec("nohup rsync -x -rlptgo --exclude=homedir/ /backup$BACKUP_NUM/cpbackup/seed/$USERNAME/ $DSTDIR/$USERNAME.seed");
		print "Linking Home to Seed\n";
		$return_value    = $cpanel->server->whm_exec("nohup rsync -x -rlptgo --link-dest=$DSTDIR/$USERNAME.home /backup$BACKUP_NUM/cpbackup/seed/$USERNAME/homedir/ $DSTDIR/$USERNAME.seed/homedir");
	}
	
	# Grab a copy of the backups
	if (!ref($backup) || $all == 1) {
		my @list;
		if (ref($backup) eq "ARRAY") {
			@list = @$backup;
			$backup = join(', ', @$backup);
		} else {
                        die "Not acceptable backup provided - please select from daily, weekly, or monthly.\n" if $backup !~ /daily|weekly|monthly/;
			push @list, $backup
		}
		print "Creating " . $backup . ".\n";
		foreach my $item (@list) {
			print "Grabbing $item...\n";
			$return_value = $cpanel->server->whm_exec("mkdir $DSTDIR/$USERNAME.$item");
			$cpanel->server->whm_exec("nohup rsync -x -rlptgo --link-dest=$DSTDIR/$USERNAME.seed /backup$BACKUP_NUM/cpbackup/$item/$USERNAME/ $DSTDIR/$USERNAME.$item");
		}
	}

	# Change ownership of files/folders
	if ($perms || $all == 1) {
		print "Change Ownership of files\n";
		my $sudo_user = $ENV{'SUDO_USER'};
		$return_value = $cpanel->server->whm_exec("chown -R $sudo_user $DSTDIR");
		print "Updating any bad permissions on files/directories\n";
		$return_value = $cpanel->server->whm_exec(qq|find $DSTDIR -xdev -type d ! -perm -500|.q| -exec chmod u+rx {} \;|);
		$return_value = $cpanel->server->whm_exec(qq|find $DSTDIR -xdev -type f ! -perm -400|.q| -exec chmod u+r {} \;|);
	}

	return 1;
}
