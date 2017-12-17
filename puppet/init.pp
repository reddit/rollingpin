Exec { path => [ '/usr/bin', '/usr/sbin', '/bin', '/usr/local/bin' ] }

exec { 'update apt cache':
  command     => 'apt-get update',
  refreshonly => true,
}

# make updating the apt cache an implicit requirement for all packages
Exec['update apt cache'] -> Package<| |>

# this makes your daemon accessible on rollingpin.local
# automatically via mDNS.
package { 'avahi-daemon':
  ensure => installed,
}

include rollingpin
