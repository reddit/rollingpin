class rollingpin {
  exec { 'add reddit ppa':
    command => 'add-apt-repository -y ppa:reddit/ppa',
    unless  => 'apt-cache policy | grep reddit/ppa',
    notify  => Exec['update apt cache'],
  }

  $dependencies = [
    'pep8',
    'python',
    'python-coverage',
    'python-mock',
    'python-twisted',
    'python-txzookeeper',
  ]

  package { $dependencies:
    ensure => installed,
    before => Exec['build app'],
  }

  exec { 'build app':
    user    => $::user,
    cwd     => $::project_path,
    command => 'python setup.py build',
    before  => Exec['install app'],
  }

  exec { 'install app':
    user    => $::user,
    cwd     => $::project_path,
    command => 'python setup.py develop --user',
  }

  file { '/etc/rollingpin.ini':
    ensure => link,
    target => "${::project_path}/example.ini",
  }

  file { '/etc/rollingpin.d':
    ensure => directory,
    owner  => 'root',
    group  => 'root',
    mode   => '0755',
  }

  file { '/etc/rollingpin.d/test.ini':
    ensure => link,
    target => "${::project_path}/example_profile.ini",
  }

  file { '/etc/profile.d/local-bin.sh':
    ensure  => file,
    content => 'export PATH=$PATH:~/.local/bin',
    owner   => 'root',
    group   => 'root',
    mode    => '0644',
  }
}
