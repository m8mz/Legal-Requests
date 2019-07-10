#!/usr/bin/perl
use strict;
use warnings;
use Getopt::Long;
use MIME::Lite;
use Proc::Daemon;
use Proc::PID::File;
use Sys::Syslog qw(:standard :macros);

BEGIN {
require '/usr/sec/lib/SecBinLog.pm';
SecBinLog::sb_log(); # Writes an entry to /var/log/legacy/sec-bin.log
}

#### TO RUN THIS SCRIPT FROM WEBPAGE PASSING IT THOUGH WHM SO IT CAN EXECUPTE THE COMMAND AND RUN IN BACKGROUND
#### /usr/sec/bin/grablogs --user=techUserName --cususer=customerUserName --domains=domain1.com --domains=domain2.com --domains=domain3.com ect..
#### Wil Return response "Running in Background. So stop hitting yourself ..." once ran which will release browser. 
#### Tech will be emailed with resuled when it finishes.


#### TO RUN THIS SCRIPT THOUGH COMMAND LINE
#### /usr/sec/bin/grablogs --v --cususer=customerUserName --domains=domain1.com --domains=domain2.com --domains=domain3.com ect..
#### You can run /usr/sec/bin/grablogs with no options and it will give you a more info.

my $pathtmpsavemain = "/tmp/"; ##
my $pathapachelogs = "/var/log/domlogs/";
my $patheximlogs = "/var/log/";
my $pathftplogs = "/var/log/";
my $pathcpanellogs = "/usr/local/cpanel/logs/";
my @domains;
my $verbose;
my $cususer;
my $tarfilename;
my $user = $ENV{'REALUSER'};
my $dryrun = 0;
my $timestamp = "";
my $force = "";
my $pathtmpsave = "";
my $gold = "\033[1;33m";
my $green = "\033[1;32m";
my $red = "\033[1;31m";
my $normal = "\033[0m";

### GRAB PASSED OPTIONS
unless (GetOptions(
        'tarfile=s'          =>  \$tarfilename,
        'domains=s'          =>   \@domains,     #set domains to grep for in logs
        'dryrun'            =>   \$dryrun,     #set debug flag
        'user=s'            =>   \$user,     #set user running script
        'cususer=s'            =>   \$cususer,     #set customer username
        'v'            =>   \$verbose,     #set debug flag
        )){ usage(); exit; }
usage() if(!$domains[0]);
usage() if(!$cususer);
usage() if(!$tarfilename);
@domains = split(/,/,join(',',@domains));
if ($user eq ""){ $user = $ENV{'SUDO_USER'}; }

if(!-t STDOUT){ #detach from our parent process if it's the web!
      print "Success";
      Proc::Daemon::Init;
}
if (Proc::PID::File->running()){
      print "I am already running!";
      exit();
}
if(!$dryrun){
   openlog("grablogs", "", LOG_LOCAL1);
   syslog("info", "User: $user has started grablogs for domains @domains");
   closelog();
}

my ($sec,$min,$hour,$mday,$mon,$year,$wday,$yday,$isdst) = localtime(time);
$year = $year +1900;
$mon = $mon + 1;
$timestamp = "$user$mon$mday$year$hour$min$sec";
$pathtmpsave = $pathtmpsavemain . $timestamp . "/";
my $savefilepathmd5 = $pathtmpsave . "md5sum.txt";
my @logs;
my @gzlogs;
my @exim;
my @gzexim;
my @ftp;
my @gzftp;
my @cpanel;
my @gzcpanel;
my $dh;

if($dryrun){
  print "$red****************************************\n";
  print "*                                      *\n";
  print "*            DRY-RUN ENABLED           *\n";
  print "*                                      *\n";
  print "****************************************$normal\n";
}

##Create Directory in TMP
if (!$dryrun){ mkdir("$pathtmpsave", 0777) || print $!; }

##APACHE LOGS
opendir($dh, $pathapachelogs) || die "can't opendir $pathapachelogs: $!";
@logs = grep { /global_log/ && !/gz/ && !/offset/ && -f "$pathapachelogs/$_" } readdir($dh);
closedir $dh;
foreach my $file (@logs) {
  chomp($file);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $file\n"; }else{
     if($verbose){ print "$gold greping .. $file ... $normal\n"; }
  }
  foreach my $dom (@domains) {
     if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $dom\n"; }else{
        if(!$dryrun){system("sudo grep $dom '/var/log/domlogs/$file' >> '$pathtmpsave$file.txt'");}
        if($verbose){ print "Parsed $dom !\n"; }
     }
  }
  if(!$dryrun){system("md5sum '$pathtmpsave$file.txt' >> '$savefilepathmd5'");}
}

opendir($dh, $pathapachelogs) || die "can't opendir $pathapachelogs: $!";
@gzlogs = grep { /global_log/ && /gz/ && -f "$pathapachelogs/$_" } readdir($dh);
closedir $dh;
foreach my $gzfile (@gzlogs) {
  chomp($gzfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $gzfile\n";}else{
     if($verbose){ print "$gold Greping .. $gzfile ... $normal\n"; }
  }   
  foreach my $gzdom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $gzdom\n"; }else{
      if(!$dryrun){system("zgrep $gzdom '/var/log/domlogs/$gzfile' >> '$pathtmpsave$gzfile.txt'");}
      if($verbose) { print "Parsed $gzdom !\n"; }
    }
  }
  if(!$dryrun){system("md5sum '$pathtmpsave$gzfile.txt' >> '$savefilepathmd5'");}
}

### EXIM LOGS
opendir($dh, $patheximlogs) || die "can't opendir $patheximlogs: $!";
@exim = grep { /exim_mainlog/ && !/gz/ && !/offset/ && -f "$patheximlogs/$_" } readdir($dh);
closedir $dh;
foreach my $exfile (@exim) {
  chomp($exfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $exfile\n";}else{
     if($verbose){ print "$gold Greping .. $exfile ... $normal\n"; }
  }
  foreach my $exdom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $exdom\n"; }else{
      if(!$dryrun){system("sudo exigrep $exdom '/var/log/$exfile' >> '$pathtmpsave$exfile.txt'");}
      if($verbose){ print "Parsed $exdom !\n"; }
    }
  }
  if(!$dryrun){system("md5sum '$pathtmpsave$exfile.txt' >> '$savefilepathmd5'");}
}


opendir($dh, $patheximlogs) || die "can't opendir $patheximlogs: $!";
@gzexim = grep { /exim_mainlog/ && /gz/ && -f "$patheximlogs/$_" } readdir($dh);
closedir $dh;
foreach my $gzexfile (@gzexim) {
  chomp($gzexfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $gzexfile\n";}else{
     if($verbose){ print "$gold Greping .. $gzexfile ... $normal\n";}
  }
  foreach my $gzexdom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $gzexdom\n"; }else{
      if(!$dryrun){system("sudo exigrep $gzexdom '/var/log/$gzexfile' >> '$pathtmpsave$gzexfile.txt'");}
      if($verbose){ print "Parsed $gzexdom !\n"; }
    }
  }
  if(!$dryrun){system("md5sum '$pathtmpsave$gzexfile.txt' >> '$savefilepathmd5'");}
}


### FTP LOGS
opendir($dh, $pathftplogs) || die "can't opendir $pathftplogs: $!";
@ftp = grep { /ftp.log/ && !/gz/ && !/offset/ && -f "$pathftplogs/$_" } readdir($dh);
closedir $dh;
foreach my $ftpfile (@ftp) {
  chomp($ftpfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $ftpfile\n";}else{
     if($verbose){ print "$gold Greping .. $ftpfile ... $normal\n"; }
  }
  foreach my $ftpdom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $ftpdom\n"; }else{
       if(!$dryrun){system("sudo grep \@$ftpdom '/var/log/$ftpfile' >> '$pathtmpsave$ftpfile.txt'");}
       if($verbose){ print "Parsed $ftpdom !\n"; }
    }
  } 
  if(!$dryrun){system("sudo grep $cususer '/var/log/$ftpfile' >> '$pathtmpsave$ftpfile.txt'");}
  if(!$dryrun){system("md5sum '$pathtmpsave$ftpfile.txt' >> '$savefilepathmd5'");}
} 


opendir($dh, $pathftplogs) || die "can't opendir $pathftplogs: $!";
@gzftp = grep { /ftp.log/ && /gz/ && -f "$pathftplogs/$_" } readdir($dh);
closedir $dh;
foreach my $gzftpfile (@gzftp) {
  chomp($gzftpfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $gzftpfile\n";}else{
     if($verbose){ print "$gold Greping .. $gzftpfile ... $normal\n";}
  }
  foreach my $gzftpdom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $gzftpdom\n"; }else{
       if(!$dryrun){system("sudo zgrep \@$gzftpdom '/var/log/$gzftpfile' >> '$pathtmpsave$gzftpfile.txt'");}
       if($verbose){ print "Parsed $gzftpdom !\n"; }
    }
  } 
  if(!$dryrun){system("sudo zgrep $cususer '/var/log/$gzftpfile' >> '$pathtmpsave$gzftpfile.txt'");}
  if(!$dryrun){system("md5sum '$pathtmpsave$gzftpfile.txt' >> '$savefilepathmd5'");}
} 

### CPANEL ACCESS LOGS
opendir($dh, $pathcpanellogs) || die "can't opendir $pathcpanellogs: $!";
@cpanel = grep { /access_log/ && !/gz/ && !/offset/ && -f "$pathcpanellogs/$_" } readdir($dh);
closedir $dh;
foreach my $cpanelfile (@cpanel) {
  chomp($cpanelfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $cpanelfile\n";}else{
     if($verbose){ print "$gold Greping .. $cpanelfile ... $normal\n"; }
  }
  foreach my $cpaneldom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $cpaneldom\n"; }else{
       if(!$dryrun){system("sudo grep $cpaneldom '/usr/local/cpanel/logs/$cpanelfile' >> '$pathtmpsave$cpanelfile.txt'");}
       if($verbose){ print "Parsed $cpaneldom !\n"; }
    }
  } 
  if(!$dryrun){system("sudo grep $cususer '/usr/local/cpanel/logs/$cpanelfile' >> '$pathtmpsave$cpanelfile.txt'");}
  if(!$dryrun){system("md5sum '$pathtmpsave$cpanelfile.txt' >> '$savefilepathmd5'");}
} 

opendir($dh, $pathcpanellogs) || die "can't opendir $pathcpanellogs: $!";
@gzcpanel = grep { /access_log/ && /gz/ && -f "$pathcpanellogs/$_" } readdir($dh);
closedir $dh;
foreach my $gzcpanelfile (@gzcpanel) {
  chomp($gzcpanelfile);
  if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping $gzcpanelfile\n";}else{
     if($verbose){ print "$gold Greping .. $gzcpanelfile ... $normal\n";}
  }
  foreach my $gzcpaneldom (@domains) {
    if($dryrun && $verbose){ print "$gold DRYRUN $normal- greping for domain $gzcpaneldom\n"; }else{
       if(!$dryrun){system("sudo zgrep $gzcpaneldom '/usr/local/cpanel/logs/$gzcpanelfile' >> '$pathtmpsave$gzcpanelfile.txt'");}
       if($verbose){ print "Parsed $gzcpaneldom !\n"; }
    }
  } 
  if(!$dryrun){system("sudo zgrep $cususer '/usr/local/cpanel/logs/$gzcpanelfile' >> '$pathtmpsave$gzcpanelfile.txt'");}
  if(!$dryrun){system("md5sum '$pathtmpsave$gzcpanelfile.txt' >> '$savefilepathmd5'");}
} 


### Tar up File
if (!$dryrun){ 
    if($verbose){ print "\n$green Taring Files ... $normal\n"; }
    system("tar -cvf $tarfilename $pathtmpsave &> /dev/null"); 
}

###CLEANUP
if (!$dryrun){
   if($verbose){ print "\n$green Cleaning up Files ... $normal\n"; }
   system("mv $pathtmpsave /GRAVEYARD/");
}

###FINISHED
if (!$dryrun){
    print "\n$green !!! FINISHED !!! $normal\n";
}

##DISPLAY USANGE WHEN NOT ALL REQUIRED OPTIONS ARE PASSED
sub usage {
print "$red
Usage $0 --cususer=<customerUsername> --domains=<domain1> --domains=<domain2>\n
Options (not required):
\t--dryrun\tdoes not actually run any commands
\t--v\t\ttoggle verbose
\n$normal";
  exit;
}
