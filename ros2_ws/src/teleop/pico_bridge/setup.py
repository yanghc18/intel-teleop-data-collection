from setuptools import setup

package_name = 'pico_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='intel-teleop-data-collection',
    maintainer_email='noreply@example.com',
    description='Pico 4 Ultra (XRoboToolkit PC Service) -> ROS 2 poses.',
    license='Apache-2.0',
    entry_points={'console_scripts': ['pico_bridge_node = pico_bridge.pico_bridge_node:main']},
)
