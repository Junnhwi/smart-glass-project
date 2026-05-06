const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, '../..');
const appNodeModules = path.resolve(projectRoot, 'node_modules');
const workspaceNodeModules = path.resolve(workspaceRoot, 'node_modules');

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [workspaceNodeModules, appNodeModules];
config.resolver.disableHierarchicalLookup = true;
config.resolver.extraNodeModules = {
  react: path.join(workspaceNodeModules, 'react'),
  'react-dom': path.join(workspaceNodeModules, 'react-dom'),
  'react-native': path.join(workspaceNodeModules, 'react-native'),
  'react-native-web': path.join(workspaceNodeModules, 'react-native-web'),
  scheduler: path.join(workspaceNodeModules, 'scheduler'),
};

module.exports = config;
